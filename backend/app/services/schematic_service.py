"""Network connectivity schematics — logical topology and straight-line diagram.

Everything here is assembled from the stored design (DesignRun / Fdh /
ServingZone / Building). Nothing re-derives engineering: port maps are the
deterministic materialisation of assignments the planning engine already made.

Port model (matches the engine's rules):
- FAT: `fat_port_count` ports, `usable_ports` available to premises after the
  spare reserve. Buildings are assigned to ports in building-code order.
- FDH: holds the 1:`fdh_split_ratio` primary splitters. When the FAT is an
  unsplit terminal (fat_split_ratio == 1) every premises consumes one splitter
  output at the FDH, so the tray map allocates splitter outputs sequentially
  across the FDH's FATs, in FAT-code order.

Lengths in the SLD are straight-line (geodesic) estimates and are labelled as
such — measured route lengths live in the cable-route plan and BOQ.
"""
import math
from collections import defaultdict

from geoalchemy2.shape import to_shape
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.building import Building
from app.db.models.design import DesignRun, Fdh, ServingZone
from app.db.models.project import Project
from app.services.pilot_service import NOC_LAT, NOC_LON

# Brand palette
NAVY = "#0D1B4B"; NAVYMID = "#1A2E72"; BRAND = "#1A6FA8"; NBLUE = "#2589C8"
SKY = "#4BAADF"; TEAL = "#00C9A7"; LIGHT = "#E8EEF6"; STEEL = "#5A739A"
AMBER = "#B45309"; WHITE = "#FFFFFF"
FONT = "DM Sans, Arial, sans-serif"
MONO = "Space Mono, Menlo, monospace"


class SchematicError(ValueError):
    """Message is safe to show the user."""


# --------------------------------------------------------------------------- #
#  Data assembly
# --------------------------------------------------------------------------- #
def _geodesic_m(lon1, lat1, lon2, lat2) -> float:
    """Equirectangular approximation — fine at district scale."""
    r = 6371000.0
    x = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    y = math.radians(lat2 - lat1)
    return r * math.hypot(x, y)


def _std_fibre(n: int) -> int:
    """Round a fibre requirement up to a standard cable size."""
    for size in (2, 4, 6, 12, 24, 48, 96, 144):
        if n <= size:
            return size
    return n


def assemble(db: Session, project: Project) -> dict:
    run = db.scalar(select(DesignRun).where(
        DesignRun.project_id == project.id, DesignRun.is_current.is_(True)))
    if run is None:
        raise SchematicError("Run a network design first.")

    fdhs = list(db.scalars(select(Fdh).where(Fdh.design_run_id == run.id)
                           .order_by(Fdh.fdh_code)))
    zones = list(db.scalars(select(ServingZone)
                            .where(ServingZone.design_run_id == run.id)
                            .order_by(ServingZone.zone_code)))
    fdh_by_id = {f.id: f for f in fdhs}

    # Buildings per zone, in code order (deterministic port assignment).
    zone_ids = [z.id for z in zones]
    bldgs = db.execute(
        select(Building.id, Building.building_code, Building.serving_zone_id,
               Building.centroid, Building.units_surveyed,
               Building.premises_estimated, Building.address,
               Building.drop_deployment)
        .where(Building.serving_zone_id.in_(zone_ids))
        .order_by(Building.building_code)).all()
    rules = run.rules or {}
    assumed_units = int(rules.get("assumed_premises_per_building", 1))
    by_zone: dict = defaultdict(list)
    for bid, code, zid, centroid, surveyed, modelled, address, deploy in bldgs:
        pt = to_shape(centroid)
        if surveyed:
            premises, src = surveyed, "surveyed"
        elif modelled:
            premises, src = modelled, "modelled"
        else:
            premises, src = assumed_units, "assumed"
        by_zone[zid].append({"code": code or "UNNUMBERED", "lon": pt.x,
                             "lat": pt.y, "premises": premises,
                             "premises_source": src,
                             "address": address or "",
                             "deployment": deploy})

    fat_ports = int(rules.get("fat_port_count", 16))
    fat_split = int(rules.get("fat_split_ratio", 1))
    fdh_split = int(rules.get("fdh_split_ratio", 32))

    # ---- per-FAT port schedule + straight-line drop lengths ----
    fats = []
    for z in zones:
        fp = to_shape(z.fat_point)
        members = by_zone.get(z.id, [])
        ports = []
        for i, b in enumerate(members, start=1):
            ports.append({
                "port": i, "building": b["code"],
                "premises": b["premises"],
                "premises_source": b["premises_source"],
                "address": b["address"],
                "deployment": b["deployment"],
                "drop_est_m": round(_geodesic_m(fp.x, fp.y, b["lon"], b["lat"]), 1),
            })
        for i in range(len(members) + 1, z.usable_ports + 1):
            ports.append({"port": i, "building": "SPARE", "drop_est_m": None})
        # Distribution fibre need: unsplit FAT carries one fibre per usable
        # port; a split FAT needs one feed fibre (+1 spare).
        dist_fibres = z.usable_ports if fat_split == 1 else 2
        fdh = fdh_by_id.get(z.fdh_id)
        fats.append({
            "code": z.zone_code, "fdh": fdh.fdh_code if fdh else None,
            "lon": fp.x, "lat": fp.y,
            "premises": z.premises_count, "buildings": z.building_count,
            "usable_ports": z.usable_ports, "spare_ports": z.spare_ports,
            "utilisation_pct": float(z.utilisation_pct),
            "avg_drop_m": float(z.avg_drop_m), "max_drop_m": float(z.max_drop_m),
            "warnings": list(z.warnings or []),
            "premises_assumed": z.premises_assumed,
            "ports": ports,
            "dist_cable_fibres": _std_fibre(dist_fibres),
        })

    # ---- per-FDH block + tray map ----
    fats_by_fdh: dict = defaultdict(list)
    for f in fats:
        if f["fdh"]:
            fats_by_fdh[f["fdh"]].append(f)

    fdh_rows = []
    for fdh in fdhs:
        members = fats_by_fdh.get(fdh.fdh_code, [])
        fp = to_shape(fdh.point)
        noc_m = _geodesic_m(NOC_LON, NOC_LAT, fp.x, fp.y)
        # Tray map: splitter outputs consumed sequentially across FATs.
        tray = []
        splitter_no, port_no = 1, 0
        for f in members:
            first = (splitter_no, port_no + 1)
            need = f["premises"] if fat_split == 1 else 1
            for _ in range(need):
                port_no += 1
                if port_no > fdh_split:
                    splitter_no += 1; port_no = 1
            tray.append({
                "fat": f["code"], "premises": f["premises"],
                "from": f"S{first[0]}:P{first[1]}",
                "to": f"S{splitter_no}:P{port_no}",
                "dist_fibres": f["dist_cable_fibres"],
                "dist_est_m": round(_geodesic_m(fp.x, fp.y, f["lon"], f["lat"]), 1),
            })
        feeder_fibres = _std_fibre(fdh.splitters + max(1, fdh.splitters // 4))
        fdh_rows.append({
            "code": fdh.fdh_code, "lon": fp.x, "lat": fp.y,
            "noc_est_m": round(noc_m, 1),
            "fats": len(members), "premises": fdh.premises_count,
            "splitters": fdh.splitters, "splitter_ratio": fdh.splitter_ratio,
            "capacity": fdh.capacity,
            "utilisation_pct": float(fdh.utilisation_pct),
            "feeder_cable_fibres": feeder_fibres,
            "tray": tray,
        })
    fdh_rows.sort(key=lambda r: r["noc_est_m"])

    return {
        "project": project.name, "prefix": project.code_prefix,
        "ran_at": run.ran_at.isoformat(), "engine": run.engine_version,
        "rules": {"fat_ports": fat_ports, "fat_split": fat_split,
                  "fdh_split": fdh_split},
        "noc": {"lon": NOC_LON, "lat": NOC_LAT},
        "fdhs": fdh_rows, "fats": fats,
    }


# --------------------------------------------------------------------------- #
#  SVG helpers
# --------------------------------------------------------------------------- #
def _esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _text(x, y, s, size=11, fill=NAVY, weight="normal", anchor="start",
          mono=False):
    fam = MONO if mono else FONT
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{_esc(fam)}" '
            f'font-size="{size}" fill="{fill}" font-weight="{weight}" '
            f'text-anchor="{anchor}">{_esc(s)}</text>')


def _rect(x, y, w, h, fill, rx=4, stroke="none", sw=0, opacity=1.0):
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" '
            f'opacity="{opacity}"/>')


def _line(x1, y1, x2, y2, stroke, w=1.5, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{stroke}" stroke-width="{w}"{d}/>')


def _header(parts, width, title, subtitle, meta):
    parts.append(_rect(0, 0, width, 74, NAVY, rx=0))
    parts.append(_text(28, 32, "AVIVA NETWORX", 18, WHITE, "bold"))
    parts.append(_text(196, 32, "networx", 12, SKY))
    parts.append(_text(28, 54, title, 13, "#A8D4EE", "bold"))
    parts.append(_text(width - 28, 32, meta, 10, "#A8D4EE", anchor="end",
                       mono=True))
    parts.append(_text(width - 28, 50, subtitle, 10, "#8FA3BF", anchor="end",
                       mono=True))


def _legend_fat_colours(parts, x, y):
    parts.append(f'<circle cx="{x}" cy="{y}" r="6" fill="{TEAL}" '
                 f'stroke="{WHITE}" stroke-width="1.5"/>')
    parts.append(_text(x + 12, y + 4, "FAT — clean", 10, STEEL))
    parts.append(f'<circle cx="{x + 110}" cy="{y}" r="6" fill="{BRAND}" '
                 f'stroke="{WHITE}" stroke-width="1.5"/>')
    parts.append(_text(x + 122, y + 4, "FAT — needs review (siting/drop/assumed premises)",
                       10, STEEL))


# --------------------------------------------------------------------------- #
#  Logical topology
# --------------------------------------------------------------------------- #
FAT_W, FAT_H, FAT_GX, FAT_GY = 104, 40, 10, 8
PER_ROW = 10
LANE_PAD = 14


def topology_svg(data: dict) -> str:
    fdhs = data["fdhs"]
    width = 320 + PER_ROW * (FAT_W + FAT_GX) + 40

    # lane heights
    lanes = []
    y = 130
    for f in fdhs:
        rows = max(1, math.ceil(len(f["tray"]) / PER_ROW))
        h = max(86, rows * (FAT_H + FAT_GY) + 24)
        lanes.append((f, y, h))
        y += h + LANE_PAD
    height = y + 60

    p: list[str] = []
    _header(p, width, f'{data["project"]} — Logical network topology',
            f'engine {data["engine"]} · ran {data["ran_at"][:10]}',
            f'{len(fdhs)} FDH · {len(data["fats"])} FAT · '
            f'{sum(f["premises"] for f in fdhs):,} premises')

    # NOC node
    p.append(_rect(28, 92, 210, 26, NAVYMID))
    p.append(_text(133, 109, f'NOC / OLT — {data["prefix"]}', 11, WHITE, "bold",
                   anchor="middle"))
    _legend_fat_colours(p, 270, 105)

    spine_x = 46
    for f, ly, lh in lanes:
        # feeder spine
        p.append(_line(spine_x, 118, spine_x, ly + 30, "#FF6A00", 2.5))
        p.append(_line(spine_x, ly + 30, 66, ly + 30, "#FF6A00", 2.5))
        # FDH block
        p.append(_rect(66, ly, 226, 60, WHITE, stroke=AMBER, sw=2))
        p.append(_text(78, ly + 18, f["code"], 12, NAVY, "bold", mono=True))
        p.append(_text(78, ly + 34,
                       f'{f["splitters"]} × 1:{f["splitter_ratio"]} splitters · '
                       f'{f["premises"]}/{f["capacity"]} prem', 9.5, STEEL))
        p.append(_text(78, ly + 50,
                       f'{f["fats"]} FATs · {f["utilisation_pct"]:.0f}% util · '
                       f'feeder {f["feeder_cable_fibres"]}F', 9.5, STEEL))
        # FATs
        for i, t in enumerate(f["tray"]):
            row, col = divmod(i, PER_ROW)
            x = 320 + col * (FAT_W + FAT_GX)
            fy = ly + row * (FAT_H + FAT_GY)
            fat = next((z for z in data["fats"] if z["code"] == t["fat"]), None)
            flagged = bool(fat and (fat["warnings"] or fat["premises_assumed"]))
            edge = BRAND if flagged else TEAL
            p.append(_line(292, ly + 30, x, fy + FAT_H / 2, "#0066FF", 1.2))
            p.append(_rect(x, fy, FAT_W, FAT_H, WHITE, stroke=edge, sw=2))
            suffix = t["fat"].rsplit("-", 1)[-1]
            p.append(_text(x + 8, fy + 16, f'FAT {suffix}', 10, NAVY, "bold",
                           mono=True))
            p.append(_text(x + 8, fy + 31,
                           f'{t["premises"]}p · {t["from"]}–{t["to"]}', 8.5, STEEL))

    p.append(_text(28, height - 26,
                   "Feeder (orange) NOC→FDH · distribution (blue) FDH→FAT · "
                   "Sx:Py = FDH splitter/output consumed · lengths in the SLD and BOQ",
                   9.5, STEEL))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}" '
            f'style="background:{WHITE}">' + "".join(p) + "</svg>")


# --------------------------------------------------------------------------- #
#  Straight-line diagram (SLD)
# --------------------------------------------------------------------------- #
def schematic_svg(data: dict) -> str:
    fdhs = data["fdhs"]
    row_h = 30
    width = 1240
    y = 150
    blocks = []
    for f in fdhs:
        h = 74 + len(f["tray"]) * row_h + 16
        blocks.append((f, y, h))
        y += h + 26
    height = y + 70

    p: list[str] = []
    _header(p, width, f'{data["project"]} — Straight-line schematic (SLD)',
            f'engine {data["engine"]} · ran {data["ran_at"][:10]}',
            "lengths are straight-line estimates — measured routes in BOQ")

    # NOC bus
    p.append(_rect(28, 96, 190, 30, NAVYMID))
    p.append(_text(123, 116, "NOC / OLT", 12, WHITE, "bold", anchor="middle"))
    bus_x = 70
    p.append(_line(bus_x, 126, bus_x, height - 60, "#FF6A00", 3))
    _legend_fat_colours(p, 260, 112)

    for f, by, bh in blocks:
        p.append(_line(bus_x, by + 26, 120, by + 26, "#FF6A00", 3))
        p.append(_text(126, by + 18, f'{f["noc_est_m"]:.0f} m (est.) · '
                       f'{f["feeder_cable_fibres"]}F feeder', 9.5, AMBER,
                       mono=True))
        # FDH cabinet block
        p.append(_rect(120, by, 300, 64, LIGHT, stroke=AMBER, sw=2))
        p.append(_text(134, by + 20, f["code"], 13, NAVY, "bold", mono=True))
        p.append(_text(134, by + 38,
                       f'{f["splitters"]} × 1:{f["splitter_ratio"]} splitters · '
                       f'{f["premises"]}/{f["capacity"]} premises', 10, STEEL))
        p.append(_text(134, by + 54,
                       f'{f["fats"]} FATs · {f["utilisation_pct"]:.0f}% utilised',
                       10, STEEL))
        # distribution legs
        table_x = 470
        p.append(_text(table_x, by + 12, "FAT", 9, STEEL, "bold", mono=True))
        p.append(_text(table_x + 110, by + 12, "SPLITTER PORTS", 9, STEEL,
                       "bold", mono=True))
        p.append(_text(table_x + 260, by + 12, "CABLE", 9, STEEL, "bold",
                       mono=True))
        p.append(_text(table_x + 360, by + 12, "LEN (EST)", 9, STEEL, "bold",
                       mono=True))
        p.append(_text(table_x + 450, by + 12, "PREM", 9, STEEL, "bold",
                       mono=True))
        p.append(_text(table_x + 520, by + 12, "DROPS AVG/MAX", 9, STEEL,
                       "bold", mono=True))
        for i, t in enumerate(f["tray"]):
            ry = by + 30 + i * row_h
            fat = next((z for z in data["fats"] if z["code"] == t["fat"]), None)
            flagged = bool(fat and (fat["warnings"] or fat["premises_assumed"]))
            edge = BRAND if flagged else TEAL
            p.append(_line(420, by + 26, 452, ry + 6, "#0066FF", 1.4))
            p.append(f'<circle cx="{458}" cy="{ry + 6}" r="5" fill="{edge}" '
                     f'stroke="{WHITE}" stroke-width="1.2"/>')
            p.append(_text(table_x, ry + 10, t["fat"], 9.5, NAVY, "bold",
                           mono=True))
            p.append(_text(table_x + 110, ry + 10, f'{t["from"]} → {t["to"]}',
                           9.5, STEEL, mono=True))
            p.append(_text(table_x + 260, ry + 10, f'{t["dist_fibres"]}F',
                           9.5, STEEL, mono=True))
            p.append(_text(table_x + 360, ry + 10, f'{t["dist_est_m"]:.0f} m',
                           9.5, STEEL, mono=True))
            p.append(_text(table_x + 450, ry + 10, str(t["premises"]), 9.5,
                           STEEL, mono=True))
            if fat:
                p.append(_text(table_x + 520, ry + 10,
                               f'{fat["avg_drop_m"]:.0f}/{fat["max_drop_m"]:.0f} m',
                               9.5, STEEL, mono=True))

    p.append(_text(28, height - 34,
                   "Sx:Py = primary splitter number : output port at the FDH. "
                   "nF = planning fibre count (standard size). Drop lengths from the design.",
                   9.5, STEEL))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}" '
            f'style="background:{WHITE}">' + "".join(p) + "</svg>")
