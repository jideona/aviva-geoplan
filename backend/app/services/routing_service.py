"""Route the pilot underground, phase by phase, and schedule the plant."""
from geoalchemy2.shape import to_shape
from shapely.geometry import LineString, Point, mapping
from shapely.ops import transform
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.design import DesignRun, Fdh, ServingZone
from app.db.models.project import Project
from app.db.models.street import Street
from app.domain.crs import STORAGE_EPSG, _transformer
from app.domain.routing import (StreetGraph, chamber_schedule, route_distribution,
                                route_feeder)
from app.services.pilot_service import NOC_LAT, NOC_LON

# Cable allowances on measured route length (SRD FR-BOQ-002).
SLACK = 0.05          # slack loops
JOINTING = 0.02       # jointing allowance
WASTAGE = 0.03        # cut wastage
CONTINGENCY = 0.05


class RoutingError(ValueError):
    """Message is safe to show the user."""


def _pilot_scope(db: Session, project: Project):
    """Split the design's FATs into phase 1 / phase 2 by the pilot plan."""
    from app.services import pilot_service
    plan = pilot_service.build(db, project)
    p1 = {f["fat_code"] for f in plan["phase1_fats"]}
    p2 = {f["fat_code"] for f in plan["phase2_fats"]}
    return p1, p2, plan


def route_phase(db: Session, project: Project, phase: int) -> dict:
    run = db.scalar(select(DesignRun).where(
        DesignRun.project_id == project.id, DesignRun.is_current.is_(True)))
    if run is None:
        raise RoutingError("Run a network design first.")

    p1, p2, _ = _pilot_scope(db, project)
    scope = p1 if phase == 1 else p2
    if not scope:
        raise RoutingError(f"Phase {phase} has no FATs in the current pilot.")
    return _quantities(db, project, run, scope, phase)


def full_quantities(db: Session, project: Project) -> dict:
    """Measured underground quantities for the WHOLE design — every FDH from
    the NOC and every FAT from its FDH — not just the pilot phases. Feeds the
    full-network SOM/BOQ."""
    run = db.scalar(select(DesignRun).where(
        DesignRun.project_id == project.id, DesignRun.is_current.is_(True)))
    if run is None:
        raise RoutingError("Run a network design first.")
    zones = list(db.scalars(select(ServingZone).where(
        ServingZone.design_run_id == run.id)))
    scope = {z.zone_code for z in zones}
    if not scope:
        raise RoutingError("The current design has no serving zones.")
    return _quantities(db, project, run, scope, phase=0)


def _quantities(db: Session, project: Project, run, scope: set[str],
                phase: int) -> dict:
    to_metric = _transformer(STORAGE_EPSG, project.metric_crs_epsg).transform

    roads = [transform(to_metric, to_shape(s.geom))
             for s in db.scalars(select(Street).where(Street.project_id == project.id))]
    if not roads:
        raise RoutingError("Import roads before routing.")
    graph = StreetGraph.from_roads(roads)

    zones = {z.zone_code: z for z in db.scalars(
        select(ServingZone).where(ServingZone.design_run_id == run.id))}
    fdhs = list(db.scalars(select(Fdh).where(Fdh.design_run_id == run.id)))

    noc = transform(to_metric, Point(NOC_LON, NOC_LAT))

    # FDHs that own at least one in-scope FAT.
    fdh_points = {}
    fdh_of_zone = {}
    for z in zones.values():
        if z.fdh_id:
            fdh_of_zone[z.zone_code] = z.fdh_id
    active_fdh = {f.id: f for f in fdhs}

    distribution = []
    total_trench = 0.0
    total_leg = 0.0
    unreachable = []
    served_fats = 0
    fdh_used = set()

    by_fdh: dict = {}
    for code in scope:
        z = zones.get(code)
        if z is None:
            continue
        fid = z.fdh_id
        by_fdh.setdefault(fid, []).append(
            (code, transform(to_metric, to_shape(z.fat_point))))

    for fid, fats in by_fdh.items():
        fdh = active_fdh.get(fid)
        if fdh is None:
            continue
        fdh_used.add(fid)
        fdh_pt = transform(to_metric, to_shape(fdh.point))
        tree = route_distribution(graph, fdh_pt, fats)
        tree.fdh_code = fdh.fdh_code
        distribution.append(tree)
        total_trench += tree.trench_length_m
        total_leg += tree.total_leg_length_m
        unreachable.extend(tree.unreachable)
        served_fats += len(tree.legs)

    # Facility laterals: FDH cabinet and FAT terminal to the nearest street
    # node. Short but real trench and cable — the BOQ must include them.
    lateral_m = 0.0
    for fid, fats in by_fdh.items():
        fdh = active_fdh.get(fid)
        if fdh is None:
            continue
        fdh_pt = transform(to_metric, to_shape(fdh.point))
        node = graph.nodes[graph.nearest_node(fdh_pt)]
        lateral_m += fdh_pt.distance(Point(node))
        for _, fp in fats:
            n = graph.nodes[graph.nearest_node(fp)]
            lateral_m += fp.distance(Point(n))

    # Feeder from NOC to each used FDH.
    feeder_fdhs = [(active_fdh[fid].fdh_code,
                    transform(to_metric, to_shape(active_fdh[fid].point)))
                   for fid in fdh_used]
    feeder = route_feeder(graph, noc, feeder_fdhs)
    feeder_len = sum(l.length_m for l in feeder)

    trench_total = total_trench + feeder_len + lateral_m
    chambers = chamber_schedule(
        noc, feeder_fdhs,
        [(c, p) for fats in by_fdh.values() for c, p in fats],
        trench_total)

    distribution_cable = _with_allowances(total_trench)
    feeder_cable = _with_allowances(feeder_len)

    return {
        "phase": phase,
        "fats_in_scope": len(scope),
        "fats_routed": served_fats,
        "fats_unreachable": unreachable,
        "fdhs": len(fdh_used),
        "feeder_length_m": round(feeder_len, 1),
        "distribution_trench_m": round(total_trench, 1),
        "lateral_trench_m": round(lateral_m, 1),
        "distribution_leg_total_m": round(total_leg, 1),
        "duct_sharing_saving_m": round(total_leg - total_trench, 1),
        "total_trench_m": round(trench_total, 1),
        "chambers": chambers,
        "cable": {
            "feeder": feeder_cable,
            "distribution": distribution_cable,
            "allowances": {"slack": SLACK, "jointing": JOINTING,
                           "wastage": WASTAGE, "contingency": CONTINGENCY},
        },
        "distribution_detail": [{
            "fdh": t.fdh_code, "fats": len(t.legs),
            "trench_m": t.trench_length_m,
            "leg_total_m": t.total_leg_length_m,
            "sharing_saving_m": t.sharing_saving_m,
        } for t in distribution],
        "note": (
            "Trench length unions shared ducts — a run serving several FATs is "
            "counted once. Cable adds slack, jointing, wastage and contingency "
            "to the measured route."
        ),
    }


def _with_allowances(measured_m: float) -> dict:
    factor = 1 + SLACK + JOINTING + WASTAGE + CONTINGENCY
    return {"measured_m": round(measured_m, 1),
            "with_allowances_m": round(measured_m * factor, 1),
            "factor": round(factor, 3)}


def quantities_for_zones(db: Session, project: Project,
                         zone_codes: set[str]) -> dict:
    """Measured underground quantities scoped to a subset of serving zones —
    used by the per-area (N/S/E/W) exports. Feeder runs to an FDH are counted
    in full for any area that contains one of its FATs, so area packs overlap
    on shared feeders (stated in the export)."""
    run = db.scalar(select(DesignRun).where(
        DesignRun.project_id == project.id, DesignRun.is_current.is_(True)))
    if run is None:
        raise RoutingError("Run a network design first.")
    if not zone_codes:
        raise RoutingError("The selected area contains no serving zones.")
    return _quantities(db, project, run, set(zone_codes), phase=0)


def feeder_ring(db: Session, project: Project) -> dict:
    """Resilience option: a closed feeder ring NOC → every FDH → NOC on the
    street graph, so any single feeder cut leaves every FDH reachable from the
    other direction (Type B PON protection pairs with this physically).

    Ordering is nearest-neighbour + 2-opt on street-graph distances — not
    provably optimal, but within a few percent at district scale. Returns the
    ring geometry for the map plus the incremental quantities against the
    as-designed feeder tree.
    """
    run = db.scalar(select(DesignRun).where(
        DesignRun.project_id == project.id, DesignRun.is_current.is_(True)))
    if run is None:
        raise RoutingError("Run a network design first.")
    fdhs = list(db.scalars(select(Fdh).where(Fdh.design_run_id == run.id)))
    if len(fdhs) < 2:
        raise RoutingError("A ring needs at least two FDHs.")

    to_metric = _transformer(STORAGE_EPSG, project.metric_crs_epsg).transform
    to_wgs = _transformer(project.metric_crs_epsg, STORAGE_EPSG).transform
    roads = [transform(to_metric, to_shape(s.geom))
             for s in db.scalars(select(Street).where(Street.project_id == project.id))]
    if not roads:
        raise RoutingError("Import roads before routing.")
    graph = StreetGraph.from_roads(roads)

    noc = transform(to_metric, Point(NOC_LON, NOC_LAT))
    sites = [("NOC", graph.nearest_node(noc))]
    for f in fdhs:
        pt = transform(to_metric, to_shape(f.point))
        sites.append((f.fdh_code, graph.nearest_node(pt)))

    # Street-graph distance matrix: one single-source Dijkstra per site.
    import math as _math
    n = len(sites)
    dmat = [[0.0] * n for _ in range(n)]
    unreachable: list[str] = []
    dists = []
    for _, node in sites:
        dist, _prev = graph.shortest_paths_from(node)
        dists.append(dist)
    for i in range(n):
        for j in range(n):
            if i != j:
                dmat[i][j] = dists[i].get(sites[j][1], _math.inf)
    reach = [i for i in range(n)
             if i == 0 or dmat[0][i] < _math.inf]
    unreachable = [sites[i][0] for i in range(1, n) if i not in reach]

    # Nearest-neighbour tour from the NOC over reachable sites.
    todo = set(reach) - {0}
    tour = [0]
    while todo:
        last = tour[-1]
        nxt = min(todo, key=lambda k: dmat[last][k])
        tour.append(nxt)
        todo.remove(nxt)

    # 2-opt improvement (NOC fixed at position 0; cycle closes back to it).
    def cycle_len(t):
        return sum(dmat[t[k]][t[(k + 1) % len(t)]] for k in range(len(t)))
    improved = True
    while improved:
        improved = False
        for a in range(1, len(tour) - 1):
            for b in range(a + 1, len(tour)):
                cand = tour[:a] + tour[a:b + 1][::-1] + tour[b + 1:]
                if cycle_len(cand) < cycle_len(tour) - 0.01:
                    tour = cand
                    improved = True

    # Geometry per leg.
    features = []
    ring_len = 0.0
    order = []
    for k in range(len(tour)):
        i, j = tour[k], tour[(k + 1) % len(tour)]
        length, edges = graph.shortest_path(sites[i][1], sites[j][1])
        ring_len += length
        order.append(sites[i][0])
        for seg in edges:
            features.append({
                "type": "Feature",
                "geometry": mapping(transform(to_wgs, seg)),
                "properties": {"kind": "ring", "seq": k,
                               "from": sites[i][0], "to": sites[j][0],
                               "leg_m": round(length, 1)}})

    # As-designed feeder tree, for the increment.
    tree_len = sum(dmat[0][i] for i in tour[1:])
    factor = 1 + SLACK + JOINTING + WASTAGE + CONTINGENCY
    summary = {
        "fdhs_on_ring": len(tour) - 1,
        "order": order + ["NOC"],
        "ring_trench_m": round(ring_len, 1),
        "tree_feeder_m": round(tree_len, 1),
        "incremental_trench_m": round(ring_len - tree_len, 1),
        "ring_cable_m": round(ring_len * factor, 1),
        "unreachable_fdhs": unreachable,
        "note": ("Ring trench may share duct with the feeder tree where routes "
                 "coincide — the increment is an upper bound. Pair with 2:N "
                 "splitters + OLT protection ports for <50 ms switchover."),
    }
    return {"type": "FeatureCollection", "features": features,
            "properties": summary}


def cable_core_schedule(db: Session, project: Project) -> dict:
    """Segment-by-segment fibre core count, feeder through distribution to
    drop — one row per physical cable run, ready for procurement.

    This does not re-derive engineering: core counts reuse the fibre-count
    model schematic_service already computes for the splitter tray map and
    port schedule (feeder_cable_fibres per FDH, dist_cable_fibres per FAT);
    this just re-presents that model as a flat, segment-ordered schedule with
    the length each specific run actually needs.

    Feeder and distribution lengths are real street-graph routed distances —
    the same route_feeder/route_distribution the BOQ's measured quantities
    use, not straight lines. Drop lengths stay straight-line ESTIMATES,
    consistent with how drop cable is treated everywhere else in this pack
    (buildings x avg drop x 1.1 in the BOQ; confirmed on survey).
    """
    from app.services import schematic_service
    run = db.scalar(select(DesignRun).where(
        DesignRun.project_id == project.id, DesignRun.is_current.is_(True)))
    if run is None:
        raise RoutingError("Run a network design first.")

    try:
        conn = schematic_service.assemble(db, project)
    except schematic_service.SchematicError as exc:
        raise RoutingError(str(exc)) from exc

    to_metric = _transformer(STORAGE_EPSG, project.metric_crs_epsg).transform
    roads = [transform(to_metric, to_shape(s.geom))
             for s in db.scalars(select(Street).where(Street.project_id == project.id))]
    if not roads:
        raise RoutingError("Import roads before routing.")
    graph = StreetGraph.from_roads(roads)

    fdhs = list(db.scalars(select(Fdh).where(Fdh.design_run_id == run.id)))
    fdh_by_code = {f.fdh_code: f for f in fdhs}
    zones = list(db.scalars(select(ServingZone).where(ServingZone.design_run_id == run.id)))
    zone_by_code = {z.zone_code: z for z in zones}

    noc = transform(to_metric, Point(NOC_LON, NOC_LAT))
    feeder_fdhs = [(f["code"], transform(to_metric, to_shape(fdh_by_code[f["code"]].point)))
                   for f in conn["fdhs"] if f["code"] in fdh_by_code]
    feeder_legs = route_feeder(graph, noc, feeder_fdhs)
    feeder_by_code = {leg.to_code: leg for leg in feeder_legs}

    factor = 1 + SLACK + JOINTING + WASTAGE + CONTINGENCY
    segments: list[dict] = []
    unreachable: list[str] = []

    for f in conn["fdhs"]:
        leg = feeder_by_code.get(f["code"])
        if leg is None:
            unreachable.append(f"feeder NOC -> {f['code']}")
            continue
        segments.append({
            "tier": "feeder", "from": "NOC", "to": f["code"],
            "cores": f["feeder_cable_fibres"], "length_m": leg.length_m,
            "with_allowances_m": round(leg.length_m * factor, 1),
            "basis": "routed",
        })

    for f in conn["fdhs"]:
        fdh = fdh_by_code.get(f["code"])
        if fdh is None:
            continue
        fdh_pt = transform(to_metric, to_shape(fdh.point))
        fats_here = [(t["fat"], transform(to_metric, to_shape(zone_by_code[t["fat"]].fat_point)))
                    for t in f["tray"] if t["fat"] in zone_by_code]
        tree = route_distribution(graph, fdh_pt, fats_here)
        leg_by_code = {leg.to_code: leg for leg in tree.legs}
        for t in f["tray"]:
            leg = leg_by_code.get(t["fat"])
            if leg is None:
                unreachable.append(f"distribution {f['code']} -> {t['fat']}")
                continue
            segments.append({
                "tier": "distribution", "from": f["code"], "to": t["fat"],
                "cores": t["dist_fibres"], "length_m": leg.length_m,
                "with_allowances_m": round(leg.length_m * factor, 1),
                "basis": "routed",
            })

    for fa in conn["fats"]:
        for p in fa["ports"]:
            if p["building"] == "SPARE" or p["drop_est_m"] is None:
                continue
            segments.append({
                "tier": "drop", "from": fa["code"], "to": p["building"],
                "cores": 1, "length_m": p["drop_est_m"],
                "with_allowances_m": round(p["drop_est_m"] * 1.1, 1),
                "basis": "estimate",
            })

    summary: dict = {}
    for s in segments:
        agg = summary.setdefault(s["tier"], {"segments": 0, "length_m": 0.0,
                                             "with_allowances_m": 0.0,
                                             "cores_total": 0})
        agg["segments"] += 1
        agg["length_m"] += s["length_m"]
        agg["with_allowances_m"] += s["with_allowances_m"]
        agg["cores_total"] += s["cores"]
    for agg in summary.values():
        agg["length_m"] = round(agg["length_m"], 1)
        agg["with_allowances_m"] = round(agg["with_allowances_m"], 1)

    return {
        "segments": segments,
        "summary": summary,
        "unreachable": unreachable,
        "note": ("Feeder and distribution lengths are street-graph routed "
                 "(measured, same as the BOQ). Drop lengths are straight-line "
                 "ESTIMATES — confirm on survey. Core counts are read from "
                 "the port schedule / splitter tray map, not re-derived here."),
    }


def routes_geojson(db: Session, project: Project, phase: int | None = None) -> dict:
    """Feeder (NOC->FDH) and distribution (FDH->FAT) route geometry for the map,
    in EPSG:4326. phase 1/2 routes only that pilot phase; phase=None routes the
    WHOLE design — every FDH from the NOC and every FAT from its FDH."""
    run = db.scalar(select(DesignRun).where(
        DesignRun.project_id == project.id, DesignRun.is_current.is_(True)))
    if run is None:
        return {"type": "FeatureCollection", "features": []}

    to_metric = _transformer(STORAGE_EPSG, project.metric_crs_epsg).transform
    to_wgs = _transformer(project.metric_crs_epsg, STORAGE_EPSG).transform

    roads = [transform(to_metric, to_shape(s.geom))
             for s in db.scalars(select(Street).where(Street.project_id == project.id))]
    graph = StreetGraph.from_roads(roads)
    zones = {z.zone_code: z for z in db.scalars(
        select(ServingZone).where(ServingZone.design_run_id == run.id))}
    fdhs = {f.id: f for f in db.scalars(select(Fdh).where(Fdh.design_run_id == run.id))}
    noc = transform(to_metric, Point(NOC_LON, NOC_LAT))

    if phase is None:
        scope = set(zones.keys())          # whole design
    else:
        p1, p2, _ = _pilot_scope(db, project)
        scope = p1 if phase == 1 else p2

    features = []

    def stub(facility: Point, kind: str, props: dict) -> None:
        """Lateral from a facility to its nearest street node, so the route
        connects to the cabinet/terminal rather than ending on the kerb."""
        node = graph.nearest_node(facility)
        nx, ny = graph.nodes[node]
        line = LineString([(facility.x, facility.y), (nx, ny)])
        if line.length > 0.5:
            features.append({"type": "Feature",
                             "geometry": mapping(transform(to_wgs, line)),
                             "properties": {"kind": kind, **props}})

    by_fdh: dict = {}
    for code in scope:
        z = zones.get(code)
        if z is not None and z.fdh_id in fdhs:
            by_fdh.setdefault(z.fdh_id, []).append(
                (code, transform(to_metric, to_shape(z.fat_point))))

    for fid, fats in by_fdh.items():
        fdh = fdhs[fid]
        fdh_pt = transform(to_metric, to_shape(fdh.point))
        tree = route_distribution(graph, fdh_pt, fats)
        for leg in tree.legs:
            for seg in leg.edges:
                features.append({
                    "type": "Feature",
                    "geometry": mapping(transform(to_wgs, seg)),
                    "properties": {"kind": "distribution", "phase": phase,
                                   "fat": leg.to_code, "fdh": fdh.fdh_code}})
        # FAT laterals: street node to the terminal.
        for code, fat_pt in fats:
            stub(fat_pt, "distribution", {"phase": phase, "fat": code,
                                          "fdh": fdh.fdh_code, "lateral": True})
        # FDH lateral: street node to the cabinet.
        stub(fdh_pt, "feeder", {"phase": phase, "fdh": fdh.fdh_code,
                                "lateral": True})

    for fid in by_fdh:
        pt = transform(to_metric, to_shape(fdhs[fid].point))
        _, edges = graph.shortest_path(graph.nearest_node(noc), graph.nearest_node(pt))
        for seg in edges:
            features.append({
                "type": "Feature",
                "geometry": mapping(transform(to_wgs, seg)),
                "properties": {"kind": "feeder", "phase": phase,
                               "fdh": fdhs[fid].fdh_code}})
    stub(noc, "feeder", {"phase": phase, "noc": True})

    features.append({"type": "Feature",
                     "geometry": mapping(transform(to_wgs, noc)),
                     "properties": {"kind": "noc", "phase": phase}})
    return {"type": "FeatureCollection", "features": features}
