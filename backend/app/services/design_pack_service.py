"""Network Design Pack — report, Schedule of Materials (SOM) and priceable BOQ,
assembled from the current design.

Nothing here re-derives engineering figures: it gathers what the design, pilot,
routing and optical engines already produced and lays them out as procurement
and construction deliverables. Quantities that are estimates (drop cable, duct
length) are labelled as such; rates are left blank for the estimator.
"""
import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.db.models.project import Project
from app.services import (design_service, inventory_service, optical_service,
                          pilot_service, routing_service, schematic_service)

NAVY = "FF0D1B4B"; NAVYMID = "FF1A2E72"; BRAND = "FF1A6FA8"; TEAL = "FF00C9A7"
AMBER = "FFB45309"; STEEL = "FF5A739A"; LIGHT = "FFF4F7FC"; WHITE = "FFFFFFFF"
DROP_SLACK = 1.10          # drop-cable estimate allowance over avg straight drop


class DesignPackError(ValueError):
    """Message is safe to show the user."""


# --------------------------------------------------------------------------- #
#  Assembly
# --------------------------------------------------------------------------- #
def assemble(db, project: Project) -> dict:
    design = design_service.current_design(db, project.id)
    if design is None:
        raise DesignPackError("Run a network design first, then export the pack.")

    fdhs = design["fdhs"]; zones = design["zones"]
    fdh_count = len(fdhs); fat_count = len(zones)
    served_buildings = sum(z["building_count"] for z in zones)
    served_premises = sum(z["premises_count"] for z in zones)
    drop_cable_m = round(sum(z["building_count"] * z["avg_drop_m"] for z in zones)
                         * DROP_SLACK, 1)

    try:
        pilot = pilot_service.build(db, project)
    except pilot_service.PilotError as exc:
        raise DesignPackError(str(exc)) from exc

    phases, missing = {}, []
    for ph in (1, 2):
        try:
            phases[ph] = routing_service.route_phase(db, project, ph)
        except routing_service.RoutingError as exc:
            missing.append(f"Phase {ph}: {exc}")
    optical = {}
    for ph in (1, 2):
        try:
            optical[ph] = optical_service.budget_report(db, project, ph)
        except Exception:                              # noqa: BLE001
            pass

    # Whole-design measured quantities (every FDH from the NOC, every FAT from
    # its FDH). Falls back to the pilot phase sums when routing is impossible.
    full = None
    try:
        full = routing_service.full_quantities(db, project)
    except routing_service.RoutingError:
        pass

    try:
        connectivity = schematic_service.assemble(db, project)
    except schematic_service.SchematicError:
        connectivity = None

    # Resilience option — priced separately, never merged into the base BOQ.
    try:
        ring = routing_service.feeder_ring(db, project)["properties"]
    except routing_service.RoutingError:
        ring = None

    # Segment-by-segment fibre core count, feeder through drop — needs the
    # same connectivity/port model as the schedules above, so it fails the
    # same way (no design run, no roads) rather than a new failure mode.
    try:
        core_schedule = routing_service.cable_core_schedule(db, project)
    except routing_service.RoutingError:
        core_schedule = None

    def s(key):
        return round(sum(p.get(key, 0) for p in phases.values()), 1)
    if full is not None:
        total_trench = full["total_trench_m"]
        feeder_cable = full["cable"]["feeder"]["with_allowances_m"]
        dist_cable = full["cable"]["distribution"]["with_allowances_m"]
        handholes = full["chambers"]["handholes"]
        fdh_manholes = full["chambers"]["manholes_at_fdh"]
        run_manholes = full["chambers"]["manholes_on_runs"]
        scope_note = "FULL NETWORK — measured routes"
    else:
        total_trench = s("total_trench_m")
        feeder_cable = round(sum(p["cable"]["feeder"]["with_allowances_m"]
                                 for p in phases.values()), 1)
        dist_cable = round(sum(p["cable"]["distribution"]["with_allowances_m"]
                               for p in phases.values()), 1)
        handholes = sum(p["chambers"]["handholes"] for p in phases.values())
        fdh_manholes = sum(p["chambers"]["manholes_at_fdh"] for p in phases.values())
        run_manholes = sum(p["chambers"]["manholes_on_runs"] for p in phases.values())
        scope_note = "PILOT PHASES 1+2 only — full-network routing unavailable"

    # ---- port-level detail (fibre counts, splices, terminations) ----
    feeder_fibres = fat_ports_total = 0
    feeder_lines: list = []
    dist_fibre_size = 12
    aerial_drops = 0
    aerial_bands: dict = {}
    underground_prem = served_premises
    deployment_note = ""
    if connectivity:
        from collections import defaultdict
        feeder_fibres = sum(f["feeder_cable_fibres"] for f in connectivity["fdhs"])
        fat_ports_total = sum(z["usable_ports"] for z in connectivity["fats"])
        sizes = sorted({f["dist_cable_fibres"] for f in connectivity["fats"]})
        dist_fibre_size = sizes[0] if len(sizes) == 1 else 0
        # Apportion measured feeder length across cable sizes by each FDH's
        # straight-line share (route factor cancels in the ratio).
        est_by_size: dict = defaultdict(float)
        for f in connectivity["fdhs"]:
            est_by_size[f["feeder_cable_fibres"]] += f["noc_est_m"]
        est_total = sum(est_by_size.values()) or 1.0
        for size in sorted(est_by_size):
            feeder_lines.append((size,
                round(feeder_cable * est_by_size[size] / est_total, 1)))
        # Drop cable from the per-port schedule (route factor 1.2 covers wall
        # runs, sag and slack), split aerial vs underground. Explicit flags
        # win; the project's aerial share applies only to unflagged drops —
        # at share 0 every unflagged drop prices as underground.
        share = float(project.aerial_drop_share or 0)
        expl_a, expl_u, unres = [], [], []
        for z in connectivity["fats"]:
            for p in z["ports"]:
                if p["building"] == "SPARE":
                    continue
                entry = ((p["drop_est_m"] or 0) * 1.2, p.get("premises") or 1)
                d = p.get("deployment")
                (expl_a if d == "aerial" else
                 expl_u if d == "underground" else unres).append(entry)
        unres_m = sum(m for m, _ in unres)
        unres_p = sum(pr for _, pr in unres)
        aerial_drops = len(expl_a) + round(len(unres) * share)
        aerial_m = sum(m for m, _ in expl_a) + unres_m * share
        underground_m = (sum(m for m, _ in expl_u) + unres_m * (1 - share))
        underground_prem = round(sum(pr for _, pr in expl_u)
                                 + unres_p * (1 - share))
        drop_cable_m = round(underground_m, 1)
        # Pre-terminated assemblies binned to standard lengths. Explicit
        # aerial drops bin individually; the assumed portion bins at the
        # average unflagged length (it is an assumption either way).
        AERIAL_BANDS = (50, 80, 100, 150, 200)
        def _band(m):
            for bd in AERIAL_BANDS:
                if m <= bd:
                    return bd
            return AERIAL_BANDS[-1]
        aerial_bands: dict = {}
        for m, _ in expl_a:
            aerial_bands[_band(m)] = aerial_bands.get(_band(m), 0) + 1
        n_assumed = round(len(unres) * share)
        if n_assumed and unres:
            avg_band = _band(unres_m / len(unres))
            aerial_bands[avg_band] = aerial_bands.get(avg_band, 0) + n_assumed
        deployment_note = (
            f"{len(expl_a)} aerial + {len(expl_u)} underground flagged; "
            f"{len(unres)} unflagged split {share:.0%} aerial by assumption")

    eq = pilot["equipment"]
    conn_fats = eq["fats"]["connectorised"]
    conv_fats = eq["fats"]["conventional"]
    splitters = {l["item"]: l for l in eq["splitters"]}

    def splq(ratio):
        return splitters.get(f"1:{ratio} splitter", {}).get("with_spares", 0)

    # ---- Schedule of Materials (procurement) ----
    som = [
        ("Active & passive equipment", [
            ("16-port XGS-PON OLT", "no.", 1, f'{eq["olt"]["ports_used"]} PON ports used'),
            ("FDH cabinet", "no.", fdh_count, "one per FDH"),
            ("FAT terminal — connectorised (pre-terminated)", "no.", conn_fats, "Phase 1"),
            ("FAT terminal — conventional (spliced)", "no.", conv_fats, "Phase 2"),
        ]),
        ("Splitters (incl. 25% spares)", [
            (l["item"], "no.", l["with_spares"],
             f'{l["role"]} · req {l["required"]} · stock {l["in_stock"]} · buy {l["buy"]}')
            for l in eq["splitters"]
        ]),
        ("Closures & terminations", [
            ("FDH splice closure", "no.", fdh_count, "one per FDH"),
            ("FAT splice closure", "no.", conv_fats, "conventional FATs only"),
            ("Drop termination / customer outlet", "no.", served_premises,
             "one per premises"),
        ] + ([
            ("SC/APC pigtail — FDH feeder termination", "no.", feeder_fibres,
             "one per feeder fibre (incl. spares)"),
            ("SC/APC pigtail — FAT port termination", "no.", fat_ports_total,
             "one per usable FAT port"),
            ("SC/APC adapter (coupler)", "no.", feeder_fibres + fat_ports_total,
             "FDH panel + FAT panel"),
            ("OLT patch cord SC/APC-SC/APC", "no.",
             (pilot["equipment"]["olt"]["ports_used"] if pilot else 0),
             "one per lit PON port"),
        ] if connectivity else [])),
        ("Cable & duct  —  " + scope_note, ([
            (f"Feeder fibre cable {size}F", "m", m,
             "measured route, apportioned by FDH share")
            for size, m in feeder_lines
        ] if feeder_lines else [
            ("Feeder fibre cable", "m", feeder_cable, "routed + allowances"),
        ]) + [
            (f"Distribution fibre cable"
             + (f" {dist_fibre_size}F" if dist_fibre_size else ""),
             "m", dist_cable, "routed + allowances"),
            ("Drop cable — underground, duct grade", "m", drop_cable_m,
             ("ESTIMATE — " + deployment_note)
             if connectivity else "ESTIMATE — buildings x avg drop x 1.1"),
        ] + [
            (f"Pre-terminated aerial drop assembly — {bd} m", "no.", qty,
             "explicit flags + assumed share; confirm lengths on survey")
            for bd, qty in sorted(aerial_bands.items())
        ] + ([
            ("Aerial drop fitting set (tension/suspension clamps, bracket)",
             "no.", aerial_drops, "one set per aerial drop — ESTIMATE"),
        ] if aerial_drops else []) + [
            ("HDPE duct", "m", total_trench, "ESTIMATE — approx = trench length"),
        ]),
        ("Chambers", [
            ("Handhole (at FAT)", "no.", handholes, ""),
            ("Manhole (at FDH)", "no.", fdh_manholes, ""),
            ("Manhole (feeder run)", "no.", run_manholes, "~200 m spacing"),
        ]),
    ]

    # ---- Bill of Quantities (measured works, priceable) ----
    boq = [
        ("A  Civil / underground works", [
            ("A1", "Trench excavation, install & reinstate", "m", total_trench),
            ("A2", "HDPE duct — supply & install (est. = trench)", "m", total_trench),
            ("A3", "Handhole chamber — at FAT", "no.", handholes),
            ("A4", "Manhole chamber — at FDH", "no.", fdh_manholes),
            ("A5", "Manhole chamber — feeder run", "no.", run_manholes),
        ]),
        ("B  Cabling", [
            ("B1", "Feeder fibre cable — pull & install", "m", feeder_cable),
            ("B2", "Distribution fibre cable — pull & install", "m", dist_cable),
            ("B3", "Drop cable — underground, install (estimate)", "m",
             drop_cable_m),
        ] + ([
            ("B4", "Pre-terminated aerial drop — hang & fit (all lengths)",
             "no.", aerial_drops),
        ] if aerial_drops else [])),
        ("C  Jointing, splitting & termination", [
            ("C1", "FDH splice closure — install & splice", "no.", fdh_count),
            ("C2", "FAT splice closure — install & splice", "no.", conv_fats),
            ("C3", "1:32 splitter — install", "no.", splq(32)),
            ("C4", "1:4 splitter — install", "no.", splq(4)),
            ("C5", "1:8 splitter — install", "no.", splq(8)),
            ("C6", "Drop termination / customer outlet", "no.", served_premises),
        ] + ([
            ("C7", "Fusion splice — feeder fibre at FDH", "no.", feeder_fibres),
            ("C8", "Fusion splice — distribution fibre at FAT", "no.",
             fat_ports_total),
            ("C9", "Fusion splice — underground drop (FAT end + outlet end)",
             "no.", underground_prem * 2),
            ("C10", "SC/APC pigtail & adapter — supply and fit", "no.",
             feeder_fibres + fat_ports_total),
        ] if connectivity else [])),
        ("D  Active equipment — install & configure", [
            ("D1", "16-port XGS-PON OLT", "no.", 1),
            ("D2", "FDH cabinet", "no.", fdh_count),
            ("D3", "FAT terminal — connectorised", "no.", conn_fats),
            ("D4", "FAT terminal — conventional", "no.", conv_fats),
        ]),
        ("E  Testing & commissioning", [
            ("E1", "OTDR / optical acceptance — per FAT", "no.", fat_count),
            ("E2", "Splice acceptance — per closure", "no.", fdh_count + conv_fats),
        ] + ([
            ("E3", "OTDR trace — per distribution fibre (OLT→FAT port)", "no.",
             fat_ports_total),
            ("E4", "Power-meter acceptance — per lit premises", "no.",
             served_premises),
        ] if connectivity else [])),
    ]

    # ---- Stock comparison — what's buildable from the uploaded warehouse
    # snapshot vs what needs buying, across the whole SOM. Splitters and
    # connectorised cable already have precise engine-level figures (from
    # pilot_service, which now reads real stock — see inventory_service);
    # bulk fibre cable and microduct compare required length against stock by
    # size; everything else uses the keyword-bucket comparison, and honestly
    # reports "no stock data" rather than a false zero where nothing matched.
    stock_comparison: list[dict] = []
    for l in eq["splitters"]:
        stock_comparison.append({
            "section": "Splitters", "item": l["item"], "uom": "no.",
            "required": l["with_spares"], "in_stock": l["in_stock"],
            "shortfall": l["buy"], "surplus": max(0, l["in_stock"] - l["with_spares"]),
            "note": l["role"],
        })
    for spec, count in eq["connectorised_cables_used"].items():
        stock_comparison.append({
            "section": "Connectorised FAT cable", "item": f"Connectorised cable — {spec}",
            "uom": "no.", "required": count, "in_stock": count, "shortfall": 0,
            "surplus": 0, "note": "Assigned from stock by tightest-fit match.",
        })
    if pilot["unserved_fats"]:
        stock_comparison.append({
            "section": "Connectorised FAT cable",
            "item": "FATs unserved by current stock/OLT capacity", "uom": "no.",
            "required": pilot["unserved_fats"], "in_stock": 0,
            "shortfall": pilot["unserved_fats"], "surplus": 0,
            "note": "See /connectorised/fit for the per-FAT reason (reach or port count).",
        })

    fibre_stock = inventory_service.stock_metres_by_fibre_count(db, project.organisation_id)
    cable_needs = list(feeder_lines) + ([(dist_fibre_size, dist_cable)] if dist_fibre_size else [])
    for size, metres_required in cable_needs:
        in_stock = fibre_stock.get(size)
        stock_comparison.append({
            "section": "Cable & Duct", "item": f"{size}F fibre cable", "uom": "m",
            "required": metres_required, "in_stock": in_stock,
            "shortfall": (round(max(0, metres_required - in_stock), 1)
                         if in_stock is not None else None),
            "surplus": (round(max(0, in_stock - metres_required), 1)
                       if in_stock is not None else None),
            "note": "" if in_stock is not None else "No matching fibre-count stock uploaded.",
        })

    microduct_stock = inventory_service.stock_metres_by_microduct_size(
        db, project.organisation_id)
    total_microduct = sum(microduct_stock.values()) if microduct_stock else None
    stock_comparison.append({
        "section": "Cable & Duct", "item": "Microduct (all sizes combined)", "uom": "m",
        "required": total_trench, "in_stock": total_microduct,
        "shortfall": (round(max(0, total_trench - total_microduct), 1)
                     if total_microduct is not None else None),
        "surplus": (round(max(0, total_microduct - total_trench), 1)
                   if total_microduct is not None else None),
        "note": ("By size: " + ", ".join(f"{k} {v:.0f}m" for k, v in microduct_stock.items())
                 if microduct_stock else "No microduct stock uploaded."),
    })

    for cl in inventory_service.compare_som_generic(db, project.organisation_id, som):
        stock_comparison.append(cl.as_dict())

    warnings = list(design.get("warnings") or []) + list(pilot.get("warnings") or [])
    if full is None:
        warnings.append("Full-network routing unavailable — SOM/BOQ quantities "
                        "cover pilot phases 1+2 only.")
    return {
        "connectivity": connectivity,
        "full_quantities": full,
        "scope_note": scope_note,
        "ring": ring,
        "project": project.name, "code_prefix": project.code_prefix,
        "design": design, "pilot": pilot, "phases": phases, "optical": optical,
        "missing_phases": missing,
        "totals": {
            "fdh_count": fdh_count, "fat_count": fat_count,
            "served_premises": served_premises, "served_buildings": served_buildings,
            "olt_ports_used": eq["olt"]["ports_used"],
            "phase1_premises": pilot["phase1_premises"],
            "phase2_premises": pilot["phase2_premises"],
            "total_trench_m": total_trench, "feeder_cable_m": feeder_cable,
            "distribution_cable_m": dist_cable, "drop_cable_m": drop_cable_m,
        },
        "som": som, "boq": boq, "warnings": warnings,
        "stock_comparison": stock_comparison,
        "core_schedule": core_schedule,
    }


# --------------------------------------------------------------------------- #
#  Methodology — how FDHs, FATs, routes and the ring were derived.
#
#  Grounded in the actual engine (app.domain.planning.engine, app.services.
#  routing_service) rather than generic prose, and parameterised with a run's
#  own saved rules, so the explanation never drifts from what the engine
#  actually did. Shared by the xlsx pack (Methodology sheet) and the Word
#  export, so the two documents never say different things.
# --------------------------------------------------------------------------- #
def methodology_sections(rules: dict, ring: dict | None) -> list[tuple[str, list[str]]]:
    prefer = ", ".join(rules.get("prefer_road_classes")
                       or ["residential", "unclassified", "tertiary", "living_street"])
    split_stage = rules.get("split_stage", "single")
    overall_split = rules.get("overall_split", rules.get("fdh_split_ratio", 32))
    anchored = rules.get("noc_anchored", False)
    _SLACK = routing_service.SLACK; _JOINTING = routing_service.JOINTING
    _WASTAGE = routing_service.WASTAGE; _CONTINGENCY = routing_service.CONTINGENCY
    total_allow = _SLACK + _JOINTING + _WASTAGE + _CONTINGENCY

    if split_stage == "single":
        splitter_para = (
            f"Single-stage split: a 1:{overall_split} splitter sits at the "
            "FDH and each FAT is a passive drop terminal with no splitter of "
            "its own, sized by physical drop-port count rather than a split "
            "ratio. Chosen to deploy from existing splitter stock without "
            "buying the smaller primaries a two-stage cascade would need.")
    else:
        splitter_para = (
            f"Two-stage split: a 1:{rules.get('fdh_split_ratio', 32)} primary splitter sits at "
            f"the FDH and a 1:{rules.get('fat_split_ratio', 1)} secondary splitter sits at each "
            f"FAT, an overall split of 1:{overall_split}. Two-stage trades a lower "
            "per-FAT port count for using primaries already in stock.")

    ring_para = (
        "A closed loop — NOC to every FDH and back to the NOC — is built "
        "as an alternative to the as-designed feeder tree, priced "
        "separately on the 'Ring option' sheet and never merged into the "
        "base BOQ. Any single feeder cut then leaves every FDH reachable "
        "from the other direction. Ordering is a nearest-neighbour tour "
        "improved by 2-opt swaps on street-graph distances — not "
        "provably optimal, but within a few percent at district scale. "
        "It pairs with Type-B 2:N protection splitters at the FDH for "
        "sub-50 ms switchover."
    ) if ring else (
        "Not generated for this pack — a feeder ring needs at least two "
        "FDHs reachable on the street graph. Generate it from Design -> "
        "Ring routing if resilience quantities are needed.")

    return [
        ("FAT SITING & SERVING-ZONE CLUSTERING", [
            "Buildings are grouped into serving zones by capacitated greedy "
            "clustering, seeded on local building density so a FAT centres on a "
            "real cluster of dwellings rather than an arbitrary split. Buildings "
            "already tagged to the same estate/parcel are pulled in before "
            "unrelated neighbours, so one compound is not scattered across "
            f"several FATs. Each cluster grows until it reaches {rules.get('usable_ports', '?')} "
            f"usable premises or exhausts buildings within {rules.get('max_drop_length_m', 150):.0f} m "
            "of the seed — this project's drop-length limit.",

            "Every zone's FAT is then snapped to the nearest road of a preferred "
            f"class ({prefer}) — a terminal sited mid-block cannot be built or "
            "reached for maintenance. Because snapping to the road can push some "
            "drops past the limit, the drop-length constraint is re-checked "
            "after placement: buildings left over the limit are pulled out and "
            "re-clustered against neighbouring zones with spare capacity, over "
            "up to four repair passes, before being left as an explicitly "
            "flagged, unassigned gap rather than a design that quietly breaches "
            "its own limit.",

            f"Zones smaller than {rules.get('min_premises_per_fat', 4)} premises are folded into "
            "their nearest neighbour instead of justifying a dedicated FAT "
            "terminal and cabinet run for a handful of homes.",
        ]),
        ("FDH GROUPING", [
            "FDH cabinets are formed by the same capacitated clustering one tier "
            "up: whole FAT zones (not individual buildings) are grouped under "
            f"each FDH's splitter budget — {rules.get('splitters_per_fdh', 3)} x "
            f"1:{rules.get('fdh_split_ratio', 32)} splitters = "
            f"{rules.get('splitters_per_fdh', 3) * rules.get('fdh_split_ratio', 32)} premises "
            "capacity per cabinet.",

            (("This design is NOC-anchored: clustering grows outward from the FDH "
              "nearest the network operations centre first, because a "
              "connectorised pilot's pre-terminated feeder cable can only reach "
              "so far — the first cabinets have to sit close to the head end."
              if anchored else
              "This design is unanchored: clustering seeds on the FAT with the "
              "densest neighbourhood of other FATs within reach, then grows "
              "outward — there is no fixed head-end constraint driving cabinet "
              "placement.") +
             f" FDH position is likewise snapped to the nearest preferred-class "
             f"road, and FDH-to-FAT distribution reach is capped at "
             f"{rules.get('max_fdh_distribution_m', 2000):.0f} m — exceeding it is flagged on "
             "the FDH schedule, not silently accepted."),
        ]),
        ("SPLITTER ALLOCATION", [
            splitter_para,
            "Splitter quantities are sized off total served premises for this "
            "design and checked against the uploaded warehouse stock (see Stock "
            "Comparison) — shortfalls are called out as a quantity to buy, never "
            "assumed away.",
        ]),
        ("ROUTE & CABLE LENGTHS", [
            "Every cable run — feeder (NOC to FDH), distribution (FDH to FAT) "
            "and drop (FAT to building) — is a real shortest path over the "
            "street graph (drops also follow traced corridors: footpaths, "
            "fences, service ways), not a straight line; a short lateral stub "
            "connects each cabinet or terminal to its nearest street node. "
            "Where the network genuinely cannot reach a building the design "
            "falls back to a straight line and flags it, so a coverage gap "
            "stays visible instead of being absorbed into an average.",

            f"Measured feeder and distribution lengths are inflated for "
            f"procurement by fixed allowances — {_SLACK:.0%} slack loops, "
            f"{_JOINTING:.0%} jointing, {_WASTAGE:.0%} cut wastage, {_CONTINGENCY:.0%} "
            f"contingency, {total_allow:.0%} total. Drop cable is a separate "
            "ESTIMATE (buildings x average drop x 1.1) until routed drops are "
            "confirmed on survey. Every tie in clustering and routing is broken "
            "by identifier rather than iteration order, so re-running the same "
            "inputs reproduces an identical design.",
        ]),
        ("FEEDER RING (resilience option)", [ring_para]),
    ]


# --------------------------------------------------------------------------- #
#  Workbook
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

def _title(ws, subtitle):
    ws["A1"] = "AVIVA NETWORX"
    ws["A1"].font = Font(name="DM Sans", size=16, bold=True, color=NAVY)
    ws["A2"] = subtitle
    ws["A2"].font = Font(name="DM Sans", size=11, color=BRAND)


def build_workbook(pack: dict) -> bytes:
    wb = Workbook()
    t = pack["totals"]; proj = pack["project"]
    ran = pack["design"].get("ran_at", ""); eng = pack["design"].get("engine_version", "")

    # ---- Design Report ----
    ws = wb.active; ws.title = "Design Report"
    ws.column_dimensions["A"].width = 40; ws.column_dimensions["B"].width = 46
    _title(ws, f"{proj} — Network Design Report")
    rows = [
        ("Design engine / run", f"v{eng} · {ran[:19].replace('T',' ')}"),
        ("", ""),
        ("NETWORK SUMMARY", ""),
        ("FDH cabinets", t["fdh_count"]),
        ("FAT terminals (serving zones)", t["fat_count"]),
        ("Premises served", t["served_premises"]),
        ("Buildings served", t["served_buildings"]),
        ("OLT PON ports used", f'{t["olt_ports_used"]} / 16'),
        ("", ""),
        ("PHASING", ""),
        ("Phase 1 — connectorised core (premises)", t["phase1_premises"]),
        ("Phase 2 — conventional extension (premises)", t["phase2_premises"]),
        ("", ""),
        ("MEASURED PLANT (routed)", ""),
        ("Quantities scope", pack.get("scope_note", "")),
        ("Total trench", f'{t["total_trench_m"]:,.0f} m'),
        ("Feeder cable (with allowances)", f'{t["feeder_cable_m"]:,.0f} m'),
        ("Distribution cable (with allowances)", f'{t["distribution_cable_m"]:,.0f} m'),
        ("Drop cable (estimate)", f'{t["drop_cable_m"]:,.0f} m'),
    ]
    r = 4
    for label, value in rows:
        if label:
            head = label.isupper()
            ws.cell(row=r, column=1, value=label).font = _font(
                bold=head, color=NAVY if head else STEEL, size=10)
            ws.cell(row=r, column=2, value=value).font = _font(color=NAVY)
        r += 1
    # optical verdicts
    if pack["optical"]:
        r += 1
        ws.cell(row=r, column=1, value="OPTICAL LOSS BUDGET").font = _font(bold=True, color=NAVY)
        r += 1
        for ph, o in sorted(pack["optical"].items()):
            wc = o.get("worst_case_path") or {}
            ws.cell(row=r, column=1, value=f"Phase {ph} — {o['architecture']}").font = _font(color=STEEL)
            ws.cell(row=r, column=2, value=(
                f"verdict {o['verdict'].upper()} · budget {o['system_budget_db']} dB · "
                f"worst {wc.get('total_loss_db','?')} dB")).font = _font(color=NAVY)
            r += 1
    # assumptions & warnings
    r += 1
    ws.cell(row=r, column=1, value="ASSUMPTIONS & NOTES").font = _font(bold=True, color=NAVY); r += 1
    notes = [
        "Drop cable and HDPE duct are ESTIMATES (drop = buildings x avg drop x 1.1; duct approx = trench).",
        "Detected/traced geometry is pilot-only until re-sourced; premises are counts, not surveyed units.",
        "Measurements are metric-CRS accurate but bounded by source geometry — planning grade, not survey grade.",
    ] + pack["missing_phases"] + pack["warnings"]
    for n in notes:
        c = ws.cell(row=r, column=1, value="• " + str(n))
        c.font = _font(size=9, italic=True, color=STEEL); c.alignment = Alignment(wrap_text=True)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
        ws.row_dimensions[r].height = 26; r += 1

    # ---- Methodology — how FDHs, FATs, routes and the ring were derived ----
    rules = pack["design"].get("rules") or {}
    ring = pack.get("ring")
    ms = wb.create_sheet("Methodology")
    ms.column_dimensions["A"].width = 18
    for col in "BCDEF":
        ms.column_dimensions[col].width = 20
    _title(ms, f"{proj} — Design Methodology")

    def _section(r, heading):
        c = ms.cell(row=r, column=1, value=heading)
        c.font = Font(name="DM Sans", size=11, bold=True, color=NAVY)
        return r + 1

    def _para(r, text):
        c = ms.cell(row=r, column=1, value=text)
        c.font = _font(size=9, color="FF2A3446")
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ms.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
        chars_per_line = 128
        lines = max(1, -(-len(text) // chars_per_line))
        ms.row_dimensions[r].height = lines * 14 + 8
        return r + 2

    r = 4
    for heading, paragraphs in methodology_sections(rules, ring):
        r = _section(r, heading)
        for p in paragraphs:
            r = _para(r, p)
        r += 1

    # ---- FDH schedule ----
    fs = wb.create_sheet("FDH schedule")
    _title(fs, f"{proj} — FDH schedule"); _hdr(fs, 4,
        ["FDH", "Premises", "FATs", "Splitters", "Capacity", "Utilisation %", "Reach m"],
        [16, 12, 8, 10, 10, 14, 10])
    r = 5
    for f in pack["design"]["fdhs"]:
        for j, v in enumerate([f["code"], f["premises"], f["fats"], f["splitters"],
                               f["capacity"], f["utilisation_pct"], round(f["reach_m"], 1)], 1):
            c = fs.cell(row=r, column=j, value=v); c.font = _font(size=9); c.border = _thin()
        r += 1

    # ---- FAT schedule ----
    zs = wb.create_sheet("FAT schedule")
    _title(zs, f"{proj} — FAT / serving-zone schedule"); _hdr(zs, 4,
        ["FAT / zone", "Premises", "Buildings", "Spare ports", "Max drop m",
         "Avg drop m", "Assumed?"], [18, 12, 12, 12, 12, 12, 10])
    r = 5
    for z in pack["design"]["zones"]:
        for j, v in enumerate([z["zone_code"], z["premises_count"], z["building_count"],
                               z["spare_ports"], z["max_drop_m"], z["avg_drop_m"],
                               "yes" if z.get("premises_assumed") else "no"], 1):
            c = zs.cell(row=r, column=j, value=v); c.font = _font(size=9); c.border = _thin()
        r += 1

    # ---- SOM ----
    ss = wb.create_sheet("SOM")
    _title(ss, f"{proj} — Schedule of Materials"); _hdr(ss, 4,
        ["Item", "Unit", "Qty", "Note"], [46, 8, 10, 44], fill=NAVYMID)
    r = 5
    for cat, items in pack["som"]:
        cc = ss.cell(row=r, column=1, value=cat)
        cc.font = _font(bold=True, color=NAVY)
        cc.fill = PatternFill("solid", fgColor=LIGHT)
        ss.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
        r += 1
        for item, unit, qty, note in items:
            for j, v in enumerate([item, unit, qty, note], 1):
                c = ss.cell(row=r, column=j, value=v)
                c.font = _font(size=9, color=AMBER if "ESTIMATE" in str(note) else "FF2A3446")
                c.border = _thin()
                if j == 3:
                    c.font = _font(size=9, bold=True, color=NAVY)
            r += 1

    # ---- Stock Comparison — buildable from warehouse stock vs needs buying ----
    cs = wb.create_sheet("Stock Comparison")
    _title(cs, f"{proj} — Stock vs. Design Requirement")
    cs["A3"] = ("Upload your warehouse stock via POST /api/v1/inventory/upload to "
               "populate this sheet with real figures. Rows with no stock data are "
               "not zero — the uploaded sheet just doesn't carry that item.")
    cs["A3"].font = _font(size=9, italic=True, color=STEEL)
    cs.merge_cells(start_row=3, start_column=1, end_row=3, end_column=8)
    _hdr(cs, 5, ["Section", "Item", "Unit", "Required", "In stock", "Shortfall (buy)",
                "Surplus", "Note / matched stock"], [22, 40, 8, 11, 11, 13, 10, 40],
        fill=NAVYMID)
    r = 6
    for line in pack["stock_comparison"]:
        in_stock = line.get("in_stock")
        shortfall = line.get("shortfall")
        surplus = line.get("surplus")
        note = line.get("note") or ""
        matched = line.get("matched_products")
        if matched:
            note = (note + " " if note else "") + "Matched: " + ", ".join(matched[:4])
        no_data = in_stock is None
        row_vals = [line["section"], line["item"], line["uom"], line["required"],
                   ("—" if no_data else in_stock),
                   ("—" if no_data else shortfall),
                   ("—" if no_data else surplus), note]
        for j, v in enumerate(row_vals, 1):
            c = cs.cell(row=r, column=j, value=v)
            c.border = _thin()
            if no_data:
                c.font = _font(size=9, italic=True, color=STEEL)
            elif j == 6 and shortfall:                       # shortfall column, non-zero
                c.font = _font(size=9, bold=True, color=AMBER)
            elif j == 7 and surplus:                          # surplus column, non-zero
                c.font = _font(size=9, color=TEAL)
            else:
                c.font = _font(size=9, color="FF2A3446")
        if no_data:
            for j in range(1, 9):
                cs.cell(row=r, column=j).fill = PatternFill("solid", fgColor=LIGHT)
        r += 1
    cs.cell(row=r + 1, column=1,
           value="Shortfall = buy quantity given current stock. Surplus = stock left "
                 "over after this design. Structured categories (splitters, "
                 "connectorised FAT cable, fibre cable by count, microduct by size) "
                 "are matched precisely; everything else uses keyword matching against "
                 "stock category/product name — verify before ordering.").font = \
        _font(size=9, italic=True, color=STEEL)

    # ---- BOQ (priceable) ----
    bs = wb.create_sheet("BOQ")
    _title(bs, f"{proj} — Bill of Quantities  (enter rates in column E)")
    _hdr(bs, 4, ["Ref", "Description", "Unit", "Qty", "Rate (NGN)", "Amount (NGN)"],
         [8, 46, 8, 12, 14, 16])
    r = 5
    subtotal_rows = []
    for sec, items in pack["boq"]:
        cc = bs.cell(row=r, column=1, value=sec)
        cc.font = _font(bold=True, color=NAVY); cc.fill = PatternFill("solid", fgColor=LIGHT)
        bs.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
        r += 1
        start = r
        for ref, desc, unit, qty in items:
            bs.cell(row=r, column=1, value=ref).font = _font(size=9, color=STEEL)
            bs.cell(row=r, column=2, value=desc).font = _font(size=9)
            bs.cell(row=r, column=3, value=unit).font = _font(size=9)
            bs.cell(row=r, column=4, value=qty).font = _font(size=9, bold=True, color=NAVY)
            bs.cell(row=r, column=5).number_format = "#,##0.00"           # rate (blank)
            amt = bs.cell(row=r, column=6, value=f"=D{r}*E{r}")
            amt.number_format = "#,##0.00"; amt.font = _font(size=9)
            for j in range(1, 7):
                bs.cell(row=r, column=j).border = _thin()
            r += 1
        st = bs.cell(row=r, column=2, value=f"{sec.split()[0]} subtotal")
        st.font = _font(bold=True, color=NAVYMID)
        sc = bs.cell(row=r, column=6, value=f"=SUM(F{start}:F{r-1})")
        sc.font = _font(bold=True, color=NAVYMID); sc.number_format = "#,##0.00"
        for j in range(1, 7):
            bs.cell(row=r, column=j).fill = PatternFill("solid", fgColor=LIGHT)
        subtotal_rows.append(r)
        r += 2
    gt = bs.cell(row=r, column=2, value="TOTAL (excl. VAT & contingency)")
    gt.font = Font(name="DM Sans", size=11, bold=True, color=WHITE)
    tc = bs.cell(row=r, column=6, value="=" + "+".join(f"F{x}" for x in subtotal_rows))
    tc.font = Font(name="DM Sans", size=11, bold=True, color=WHITE); tc.number_format = "#,##0.00"
    for j in range(1, 7):
        bs.cell(row=r, column=j).fill = PatternFill("solid", fgColor=NAVY)
    bs.cell(row=r + 2, column=2,
            value="Rates are left blank for the estimator. Amounts compute automatically. "
                  "Quantities marked estimate (drop cable, duct) should be confirmed on site.").font = \
        _font(size=9, italic=True, color=STEEL)

    # ---- FAT port schedule (connection detail per terminal) ----
    conn = pack.get("connectivity")
    if conn:
        ps = wb.create_sheet("FAT port schedule")
        _title(ps, f"{proj} — FAT port assignment schedule")
        ps["A3"] = ("Ports are assigned in building-code order. Drop lengths are "
                    "straight-line estimates; measured drops are in the drops layer.")
        ps["A3"].font = _font(size=9, italic=True, color=STEEL)
        _hdr(ps, 4, ["FAT", "FDH", "Port", "Building / status", "Premises",
                     "Drop est. m", "Zone util %", "Flags"],
             [18, 16, 7, 22, 9, 11, 11, 34])
        r = 5
        for z in conn["fats"]:
            flags = "; ".join(z["warnings"]) or (
                "premises assumed" if z["premises_assumed"] else "")
            for port in z["ports"]:
                spare = port["building"] == "SPARE"
                vals = [z["code"], z["fdh"], port["port"], port["building"],
                        port.get("premises"),
                        port["drop_est_m"], round(z["utilisation_pct"], 1),
                        flags if port["port"] == 1 else ""]
                for j, v in enumerate(vals, 1):
                    c = ps.cell(row=r, column=j, value=v)
                    c.font = _font(size=9, color=STEEL if spare else "FF2A3446")
                    c.border = _thin()
                r += 1

        # ---- Building connection schedule (building-first view) ----
        bc = wb.create_sheet("Building connections")
        _title(bc, f"{proj} — Building-to-FAT connection schedule")
        bc["A3"] = ("One row per connected building, in code order. Premises "
                    "source: surveyed (field), modelled (typology), assumed "
                    "(rule default — treat as a lower bound). Drop lengths are "
                    "straight-line estimates.")
        bc["A3"].font = _font(size=9, italic=True, color=STEEL)
        _hdr(bc, 4, ["Building code", "Address", "FAT", "FAT port", "FDH",
                     "Premises", "Count source", "Drop est. m", "Drop type",
                     "Zone flags"],
             [20, 26, 18, 8, 16, 9, 11, 10, 12, 30])
        r = 5
        rows = []
        for z in conn["fats"]:
            flags = "; ".join(z["warnings"]) or (
                "premises assumed" if z["premises_assumed"] else "")
            for port in z["ports"]:
                if port["building"] == "SPARE":
                    continue
                rows.append((port["building"], port.get("address", ""),
                             z["code"], port["port"], z["fdh"],
                             port.get("premises"),
                             port.get("premises_source", ""),
                             port["drop_est_m"],
                             port.get("deployment") or "unset", flags))
        rows.sort(key=lambda x: x[0])
        for vals in rows:
            assumed = vals[6] == "assumed"
            for j, v in enumerate(vals, 1):
                c = bc.cell(row=r, column=j, value=v)
                c.font = _font(size=9,
                               color=AMBER if (assumed and j in (6, 7))
                               else "FF2A3446")
                c.border = _thin()
            r += 1
        bc.cell(row=r + 1, column=1,
                value=f"{len(rows):,} connected buildings · "
                      f"{sum(v[5] or 0 for v in rows):,} premises").font = \
            _font(size=9, bold=True, color=NAVY)

        # ---- FDH tray map (primary splitter output allocation) ----
        tm = wb.create_sheet("FDH tray map")
        _title(tm, f"{proj} — FDH splitter tray map")
        tm["A3"] = ("Sx:Py = splitter number : output port. Outputs are consumed "
                    "sequentially across the FDH's FATs in code order.")
        tm["A3"].font = _font(size=9, italic=True, color=STEEL)
        _hdr(tm, 4, ["FDH", "FAT", "Premises", "Splitter ports (from → to)",
                     "Distribution cable", "Length est. m", "Feeder cable"],
             [16, 18, 10, 22, 16, 12, 12])
        r = 5
        for f in conn["fdhs"]:
            for i, t in enumerate(f["tray"]):
                vals = [f["code"], t["fat"], t["premises"],
                        f'{t["from"]} → {t["to"]}', f'{t["dist_fibres"]}F',
                        t["dist_est_m"],
                        f'{f["feeder_cable_fibres"]}F' if i == 0 else ""]
                for j, v in enumerate(vals, 1):
                    c = tm.cell(row=r, column=j, value=v)
                    c.font = _font(size=9)
                    c.border = _thin()
                r += 1

    # ---- Cable Core Schedule (segment-by-segment fibre core count) ----
    core_schedule = pack.get("core_schedule")
    if core_schedule:
        cc = wb.create_sheet("Cable Core Schedule")
        _title(cc, f"{proj} — Cable Core Schedule")
        cc["A3"] = core_schedule.get("note", "")
        cc["A3"].font = _font(size=9, italic=True, color=STEEL)
        cc.merge_cells(start_row=3, start_column=1, end_row=3, end_column=6)
        _hdr(cc, 5, ["Tier", "From", "To", "Cores", "Length m", "With allowances m"],
            [14, 14, 20, 8, 12, 16], fill=NAVYMID)
        r = 6
        tier_fill = {"feeder": NAVY, "distribution": BRAND, "drop": STEEL}
        for seg in core_schedule["segments"]:
            vals = [seg["tier"], seg["from"], seg["to"], seg["cores"],
                    seg["length_m"], seg["with_allowances_m"]]
            for j, v in enumerate(vals, 1):
                c = cc.cell(row=r, column=j, value=v)
                c.font = _font(size=9,
                              bold=(j == 1),
                              color=tier_fill.get(seg["tier"], "FF2A3446") if j == 1
                              else "FF2A3446")
                c.border = _thin()
            r += 1
        r += 1
        for tier, agg in core_schedule["summary"].items():
            cc.cell(row=r, column=1, value=f"{tier.upper()} total").font = \
                _font(bold=True, color=NAVY)
            cc.cell(row=r, column=2, value=f'{agg["segments"]} segments').font = _font(color=STEEL)
            cc.cell(row=r, column=5, value=agg["length_m"]).font = _font(bold=True, color=NAVY)
            cc.cell(row=r, column=6, value=agg["with_allowances_m"]).font = _font(bold=True, color=NAVY)
            r += 1
        if core_schedule.get("unreachable"):
            r += 1
            cc.cell(row=r, column=1,
                   value="Unreachable on street graph: "
                         + "; ".join(core_schedule["unreachable"])).font = \
                _font(size=9, color=AMBER)

    # ---- Ring option (resilience — priced as an alternative, not in totals) --
    ring = pack.get("ring")
    if ring:
        rs = wb.create_sheet("Ring option")
        _title(rs, f"{proj} — Feeder ring resilience option")
        rs["A3"] = ("Closed feeder loop NOC → every FDH → NOC. Any single "
                    "feeder cut leaves all FDHs reachable from the other "
                    "direction. Quantities are INCREMENTAL to the base design "
                    "and are NOT included in the BOQ totals.")
        rs["A3"].font = _font(size=9, italic=True, color=STEEL)
        _hdr(rs, 5, ["Item", "Unit", "Qty", "Note"], [46, 8, 14, 46],
             fill=NAVYMID)
        eqp = pack["pilot"]["equipment"] if pack.get("pilot") else {}
        splq32 = 0
        for l in (eqp.get("splitters") or []):
            if l["item"] == "1:32 splitter":
                splq32 = l["with_spares"]
        rows = [
            ("FDHs on ring", "no.", ring["fdhs_on_ring"],
             " → ".join(ring["order"][:8]) + (" …" if len(ring["order"]) > 9 else "")),
            ("Ring route length (trench basis)", "m", ring["ring_trench_m"],
             "street-routed closed loop"),
            ("As-designed feeder tree (compare)", "m", ring["tree_feeder_m"],
             "sum of NOC→FDH shortest paths"),
            ("Incremental trench (upper bound)", "m",
             ring["incremental_trench_m"],
             "less where ring shares duct with tree routes"),
            ("Ring feeder cable (with allowances)", "m", ring["ring_cable_m"],
             "slack + jointing + wastage + contingency"),
            ("2:N protection splitters (Type B, option)", "no.", splq32,
             "replaces 1:32 units at FDHs for <50 ms switchover"),
            ("OLT protection PON ports (option)", "no.",
             pack["totals"].get("olt_ports_used", 0),
             "one protection port per working port"),
        ]
        r = 6
        for item, unit, qty, note in rows:
            for j, v in enumerate([item, unit, qty, note], 1):
                c = rs.cell(row=r, column=j, value=v)
                c.font = _font(size=9, bold=(j == 3), color=NAVY if j == 3 else "FF2A3446")
                c.border = _thin()
            r += 1
        if ring.get("unreachable_fdhs"):
            rs.cell(row=r + 1, column=1,
                    value="Unreachable on street graph: "
                          + ", ".join(ring["unreachable_fdhs"])).font = \
                _font(size=9, color=AMBER)
        rs.cell(row=r + 2, column=1, value=ring.get("note", "")).font = \
            _font(size=9, italic=True, color=STEEL)

    buf = io.BytesIO(); wb.save(buf)
    return buf.getvalue()
