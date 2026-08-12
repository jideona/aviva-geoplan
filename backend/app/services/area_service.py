"""North / South / East / West segmentation of the designed area, and the
per-area export pack.

Assignment is per SERVING ZONE (FAT), never per building — a FAT and all the
buildings it serves stay in one area, so an area pack is always buildable as a
unit. A zone's quadrant comes from the bearing of its FAT point relative to
the design centre (the boundary centroid): |Δlat| ≥ |Δlon·cos(lat)| decides
North/South, otherwise East/West.

Feeder caveat: an FDH may serve FATs in more than one quadrant. Each area
counts the full NOC→FDH feeder for every FDH that serves it, so summing the
four area packs double-counts shared feeders — the district totals in the main
design pack remain the authoritative whole-network figures.
"""
import io
import math

from geoalchemy2.shape import to_shape
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from shapely.geometry import box, mapping
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.boundary import ProjectBoundary
from app.db.models.project import Project
from app.services import routing_service, schematic_service

QUADRANTS = ("north", "south", "east", "west")

NAVY = "FF0D1B4B"; NAVYMID = "FF1A2E72"; BRAND = "FF1A6FA8"
STEEL = "FF5A739A"; LIGHT = "FFF4F7FC"; WHITE = "FFFFFFFF"; AMBER = "FFB45309"


class AreaError(ValueError):
    """Message is safe to show the user."""


# --------------------------------------------------------------------------- #
#  Segmentation
# --------------------------------------------------------------------------- #
def _centre(db: Session, project: Project):
    b = db.scalar(select(ProjectBoundary).where(
        ProjectBoundary.project_id == project.id,
        ProjectBoundary.is_current.is_(True)))
    if b is None:
        raise AreaError("Upload a project boundary first.")
    shp = to_shape(b.geom)
    c = shp.centroid
    return c.x, c.y, shp


def quadrant_of(lon: float, lat: float, cx: float, cy: float) -> str:
    dx = (lon - cx) * math.cos(math.radians(cy))
    dy = lat - cy
    if abs(dy) >= abs(dx):
        return "north" if dy >= 0 else "south"
    return "east" if dx >= 0 else "west"


def _fats_by_quadrant(db: Session, project: Project):
    conn = schematic_service.assemble(db, project)
    cx, cy, boundary = _centre(db, project)
    out: dict[str, list] = {q: [] for q in QUADRANTS}
    for f in conn["fats"]:
        out[quadrant_of(f["lon"], f["lat"], cx, cy)].append(f)
    return conn, out, cx, cy, boundary


def areas_geojson(db: Session, project: Project) -> dict:
    """Quadrant polygons (boundary ∩ quadrant bbox) with per-area counts."""
    conn, by_q, cx, cy, boundary = _fats_by_quadrant(db, project)
    minx, miny, maxx, maxy = boundary.bounds
    pad = 0.002
    rects = {
        "north": box(minx - pad, cy, maxx + pad, maxy + pad),
        "south": box(minx - pad, miny - pad, maxx + pad, cy),
        "east": box(cx, miny - pad, maxx + pad, maxy + pad),
        "west": box(minx - pad, miny - pad, cx, maxy + pad),
    }
    # East/west own only the halves not claimed by north/south: intersect with
    # the diagonal split. Simpler and visually clear: clip N/S to the full
    # width, then remove their claim from E/W using the |dy|>=|dx| rule is
    # overkill for display — the counts (below) are the authoritative
    # assignment; polygons are orientation guides.
    features = []
    for q in QUADRANTS:
        poly = boundary.intersection(rects[q])
        if poly.is_empty:
            continue
        fats = by_q[q]
        features.append({
            "type": "Feature",
            "geometry": mapping(poly),
            "properties": {
                "area": q,
                "label": q.upper(),
                "fats": len(fats),
                "buildings": sum(f["buildings"] for f in fats),
                "premises": sum(f["premises"] for f in fats),
            },
        })
    return {"type": "FeatureCollection", "features": features,
            "properties": {"centre": [cx, cy],
                           "note": ("Counts assign each FAT (and all its "
                                    "buildings) to exactly one area by bearing "
                                    "from the boundary centroid. Polygons are "
                                    "orientation guides; N/S halves overlap "
                                    "E/W at the edges.")}}


# --------------------------------------------------------------------------- #
#  Per-area workbook
# --------------------------------------------------------------------------- #
def _font(**kw):
    kw.setdefault("name", "DM Sans"); kw.setdefault("size", 10)
    return Font(**kw)


def _thin():
    s = Side(style="thin", color="FFD6DEEA")
    return Border(left=s, right=s, top=s, bottom=s)


def _hdr(ws, row, headers, widths, fill=NAVY):
    for i, (h, w) in enumerate(zip(headers, widths), start=1):
        c = ws.cell(row=row, column=i, value=h)
        c.font = Font(name="Space Mono", size=9, bold=True, color=WHITE)
        c.fill = PatternFill("solid", fgColor=fill)
        c.alignment = Alignment(vertical="center", wrap_text=True)
        c.border = _thin()
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[row].height = 26


def area_pack(db: Session, project: Project, quadrant: str) -> bytes:
    quadrant = quadrant.lower()
    if quadrant not in QUADRANTS:
        raise AreaError(f"Area must be one of {', '.join(QUADRANTS)}.")
    conn, by_q, _cx, _cy, _b = _fats_by_quadrant(db, project)
    fats = by_q[quadrant]
    if not fats:
        raise AreaError(f"No serving zones fall in the {quadrant} area.")
    codes = {f["code"] for f in fats}
    fdh_codes = sorted({f["fdh"] for f in fats if f["fdh"]})
    try:
        qty = routing_service.quantities_for_zones(db, project, codes)
    except routing_service.RoutingError as exc:
        raise AreaError(str(exc)) from exc

    buildings = sum(f["buildings"] for f in fats)
    premises = sum(f["premises"] for f in fats)
    drop_m = round(sum((p["drop_est_m"] or 0) * 1.2
                       for f in fats for p in f["ports"]
                       if p["building"] != "SPARE"), 1)

    wb = Workbook()

    # ---- Summary ----
    ws = wb.active; ws.title = "Area summary"
    ws.column_dimensions["A"].width = 42; ws.column_dimensions["B"].width = 40
    ws["A1"] = "AVIVA NETWORX"
    ws["A1"].font = Font(name="DM Sans", size=16, bold=True, color=NAVY)
    ws["A2"] = f"{project.name} — {quadrant.upper()} area pack"
    ws["A2"].font = Font(name="DM Sans", size=11, color=BRAND)
    rows = [
        ("Serving zones (FATs)", len(fats)),
        ("FDHs serving this area", ", ".join(fdh_codes)),
        ("Buildings", buildings),
        ("Premises", premises),
        ("", ""),
        ("MEASURED (routed, this area's zones)", ""),
        ("Total trench", f'{qty["total_trench_m"]:,.0f} m'),
        ("Feeder cable (with allowances)",
         f'{qty["cable"]["feeder"]["with_allowances_m"]:,.0f} m'),
        ("Distribution cable (with allowances)",
         f'{qty["cable"]["distribution"]["with_allowances_m"]:,.0f} m'),
        ("Drop cable (per-port estimate x 1.2)", f"{drop_m:,.0f} m"),
        ("Handholes / FDH manholes / run manholes",
         f'{qty["chambers"]["handholes"]} / '
         f'{qty["chambers"]["manholes_at_fdh"]} / '
         f'{qty["chambers"]["manholes_on_runs"]}'),
    ]
    r = 4
    for label, value in rows:
        if label:
            head = label.isupper()
            ws.cell(row=r, column=1, value=label).font = _font(
                bold=head, color=NAVY if head else STEEL)
            ws.cell(row=r, column=2, value=value).font = _font(color=NAVY)
        r += 1
    ws.cell(row=r + 1, column=1, value=(
        "Feeder runs are counted in full for every FDH serving this area; an "
        "FDH shared with another area appears in both packs. District totals "
        "live in the main design pack.")).font = _font(size=9, italic=True,
                                                       color=STEEL)

    # ---- Priceable area BOQ ----
    bs = wb.create_sheet("Area BOQ")
    bs["A1"] = f"{project.name} — {quadrant.upper()} BOQ (enter rates in E)"
    bs["A1"].font = Font(name="DM Sans", size=13, bold=True, color=NAVY)
    _hdr(bs, 3, ["Ref", "Description", "Unit", "Qty", "Rate (NGN)",
                 "Amount (NGN)"], [8, 46, 8, 12, 14, 16])
    items = [
        ("A1", "Trench excavation, install & reinstate", "m",
         qty["total_trench_m"]),
        ("A2", "HDPE duct (est. = trench)", "m", qty["total_trench_m"]),
        ("A3", "Handhole chamber — at FAT", "no.", qty["chambers"]["handholes"]),
        ("A4", "Manhole chamber — at FDH", "no.",
         qty["chambers"]["manholes_at_fdh"]),
        ("A5", "Manhole chamber — feeder run", "no.",
         qty["chambers"]["manholes_on_runs"]),
        ("B1", "Feeder fibre cable — pull & install", "m",
         qty["cable"]["feeder"]["with_allowances_m"]),
        ("B2", "Distribution fibre cable — pull & install", "m",
         qty["cable"]["distribution"]["with_allowances_m"]),
        ("B3", "Drop cable — install (estimate)", "m", drop_m),
        ("C1", "FAT terminal — install", "no.", len(fats)),
        ("C2", "Fusion splice — distribution at FAT", "no.",
         sum(f["usable_ports"] for f in fats)),
        ("C3", "Drop termination / customer outlet", "no.", premises),
        ("C4", "Fusion splice — drop (both ends)", "no.", premises * 2),
        ("E1", "OTDR / optical acceptance — per FAT", "no.", len(fats)),
        ("E2", "Power-meter acceptance — per premises", "no.", premises),
    ]
    r = 4
    for ref, desc, unit, q_ in items:
        bs.cell(row=r, column=1, value=ref).font = _font(size=9, color=STEEL)
        bs.cell(row=r, column=2, value=desc).font = _font(size=9)
        bs.cell(row=r, column=3, value=unit).font = _font(size=9)
        bs.cell(row=r, column=4, value=q_).font = _font(size=9, bold=True,
                                                        color=NAVY)
        bs.cell(row=r, column=5).number_format = "#,##0.00"
        amt = bs.cell(row=r, column=6, value=f"=D{r}*E{r}")
        amt.number_format = "#,##0.00"; amt.font = _font(size=9)
        for j in range(1, 7):
            bs.cell(row=r, column=j).border = _thin()
        r += 1
    tot = bs.cell(row=r, column=2, value="AREA TOTAL")
    tot.font = Font(name="DM Sans", size=11, bold=True, color=WHITE)
    tc = bs.cell(row=r, column=6, value=f"=SUM(F4:F{r-1})")
    tc.font = Font(name="DM Sans", size=11, bold=True, color=WHITE)
    tc.number_format = "#,##0.00"
    for j in range(1, 7):
        bs.cell(row=r, column=j).fill = PatternFill("solid", fgColor=NAVY)

    # ---- FAT schedule ----
    zs = wb.create_sheet("FAT schedule")
    zs["A1"] = f"{quadrant.upper()} — FAT / serving-zone schedule"
    zs["A1"].font = Font(name="DM Sans", size=13, bold=True, color=NAVY)
    _hdr(zs, 3, ["FAT", "FDH", "Premises", "Buildings", "Spare ports",
                 "Avg drop m", "Max drop m", "Flags"],
         [18, 16, 10, 10, 11, 10, 10, 34])
    r = 4
    for f in sorted(fats, key=lambda x: x["code"]):
        flags = "; ".join(f["warnings"]) or (
            "premises assumed" if f["premises_assumed"] else "")
        for j, v in enumerate([f["code"], f["fdh"], f["premises"],
                               f["buildings"], f["spare_ports"],
                               f["avg_drop_m"], f["max_drop_m"], flags], 1):
            c = zs.cell(row=r, column=j, value=v)
            c.font = _font(size=9); c.border = _thin()
        r += 1

    # ---- Building connections ----
    bc = wb.create_sheet("Building connections")
    bc["A1"] = f"{quadrant.upper()} — building-to-FAT connections"
    bc["A1"].font = Font(name="DM Sans", size=13, bold=True, color=NAVY)
    _hdr(bc, 3, ["Building code", "FAT", "Port", "FDH", "Premises",
                 "Count source", "Drop est. m", "Drop type"],
         [20, 18, 7, 16, 9, 11, 10, 12])
    r = 4
    brows = []
    for f in fats:
        for p in f["ports"]:
            if p["building"] == "SPARE":
                continue
            brows.append((p["building"], f["code"], p["port"], f["fdh"],
                          p.get("premises"), p.get("premises_source", ""),
                          p["drop_est_m"], p.get("deployment") or "unset"))
    for vals in sorted(brows):
        for j, v in enumerate(vals, 1):
            c = bc.cell(row=r, column=j, value=v)
            c.font = _font(size=9); c.border = _thin()
        r += 1

    buf = io.BytesIO(); wb.save(buf)
    return buf.getvalue()
