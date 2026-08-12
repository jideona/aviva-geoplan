"""Run the planning engine against a project and persist the result."""
import uuid

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import MultiPoint, Point
from shapely.ops import transform
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models.building import Building
from app.db.models.design import DesignRun, Fdh, ServingZone
from app.db.models.project import Project
from app.db.models.street import Street
from app.db.models.user import User
from app.domain.crs import STORAGE_EPSG, _transformer
from app.domain.planning.engine import PlanningError, plan
from app.domain.planning.model import PlanningBuilding, PlanningRoad
from app.domain.planning.rules import DesignRules
from app.services import audit_service


class DesignError(ValueError):
    """Message is safe to show the user."""


def run_design(db: Session, user: User, project: Project,
               rules: DesignRules) -> dict:
    to_metric = _transformer(STORAGE_EPSG, project.metric_crs_epsg).transform
    to_wgs = _transformer(project.metric_crs_epsg, STORAGE_EPSG).transform

    buildings = list(db.scalars(
        select(Building).where(Building.project_id == project.id,
                               Building.excluded.is_(False))))
    if not buildings:
        raise DesignError("Import buildings before running a design.")

    planning_buildings = []
    for b in buildings:
        # Preference order: surveyed, then modelled, then the rule assumption.
        if b.units_surveyed:
            premises, assumed = b.units_surveyed, False
        elif b.premises_estimated:
            premises, assumed = b.premises_estimated, False
        else:
            premises, assumed = rules.assumed_premises_per_building, True
        planning_buildings.append(PlanningBuilding(
            id=str(b.id), point=transform(to_metric, to_shape(b.centroid)),
            premises=premises, premises_is_assumed=assumed,
            code=b.building_code,
            street_id=str(b.street_id) if b.street_id else None,
            group_id=str(b.parcel_id) if b.parcel_id else None))

    roads = [
        PlanningRoad(id=str(s.id),
                     geometry=transform(to_metric, to_shape(s.geom)),
                     road_class=s.road_class)
        for s in db.scalars(select(Street).where(Street.project_id == project.id))
    ]

    try:
        result = plan(planning_buildings, roads, rules)
    except PlanningError as exc:
        raise DesignError(str(exc)) from exc

    # Supersede the previous design rather than deleting it, so a design that
    # has been quoted or issued remains retrievable.
    db.execute(update(DesignRun)
               .where(DesignRun.project_id == project.id,
                      DesignRun.is_current.is_(True))
               .values(is_current=False))
    # Clear BOTH the zone link and the building code before re-numbering.
    # Codes are regenerated every run; leaving stale ones (e.g. on buildings
    # since excluded by cleanup) collides with the fresh WUY-FAT-xxx-Byy codes
    # on the unique (project_id, building_code) constraint.
    db.execute(update(Building)
               .where(Building.project_id == project.id)
               .values(serving_zone_id=None, building_code=None))

    # Store the FULL rule set (not just the engine's summary) so a re-run can
    # faithfully reproduce this design — including Pilot mode (noc_anchor) and
    # the reach limits the summary omits. Without this, one-click re-run would
    # silently drop settings and move cabinets.
    stored_rules = {
        **result.rules_applied,
        "noc_anchored": rules.noc_anchor is not None,
        "fat_split_ratio": rules.fat_split_ratio,
        "min_premises_per_fat": rules.min_premises_per_fat,
        "max_fdh_distribution_m": rules.max_fdh_distribution_m,
        "max_fat_road_offset_m": rules.max_fat_road_offset_m,
    }
    run = DesignRun(
        project_id=project.id, engine_version=result.engine_version,
        rules=stored_rules, summary=result.summary(),
        warnings=result.warnings, run_by=user.email, is_current=True)
    db.add(run)
    db.flush()

    # FDHs first, so serving zones can reference them.
    fdh_by_suffix: dict[str, Fdh] = {}
    for f in result.fdhs:
        row = Fdh(
            project_id=project.id, design_run_id=run.id,
            fdh_code=f"{project.code_prefix}-{f.code_suffix}",
            point=from_shape(transform(to_wgs, f.point), srid=4326),
            fat_count=len(f.fat_codes), premises_count=f.premises,
            splitters=f.splitters, splitter_ratio=f.splitter_ratio,
            capacity=f.capacity, utilisation_pct=f.utilisation_pct,
            max_distribution_m=f.max_distribution_m,
            road_offset_m=f.road_offset_m)
        db.add(row)
        db.flush()
        for fat_suffix in f.fat_codes:
            fdh_by_suffix[fat_suffix] = row

    by_id = {str(b.id): b for b in buildings}
    for zone in result.zones:
        points = [planning_point(by_id[bid], to_metric) for bid in zone.building_ids]
        extent = None
        if len(points) >= 3:
            hull = MultiPoint(points).convex_hull
            if hull.geom_type == "Polygon":
                extent = from_shape(transform(to_wgs, hull), srid=4326)

        utilisation = (zone.premises / rules.usable_ports * 100
                       if rules.usable_ports else 0)
        row = ServingZone(
            project_id=project.id, design_run_id=run.id,
            zone_code=f"{project.code_prefix}-{zone.code_suffix}",
            fat_point=from_shape(transform(to_wgs, zone.fat_point), srid=4326),
            extent=extent,
            building_count=len(zone.building_ids), premises_count=zone.premises,
            splitter_ratio=rules.fat_splitter_ratio,
            usable_ports=rules.usable_ports,
            spare_ports=max(0, rules.usable_ports - zone.premises),
            utilisation_pct=round(utilisation, 1),
            max_drop_m=zone.max_drop_m, avg_drop_m=zone.avg_drop_m,
            road_id=uuid.UUID(zone.road_id) if zone.road_id else None,
            road_offset_m=zone.road_offset_m,
            premises_assumed=any(
                b.premises_is_assumed for b in planning_buildings
                if b.id in set(zone.building_ids)),
            warnings=zone.warnings,
        )
        parent = fdh_by_suffix.get(zone.code_suffix)
        if parent is not None:
            row.fdh_id = parent.id
        db.add(row)
        db.flush()
        # Number each building within its FAT, so the code itself says which FAT
        # serves it: WUY-FAT-007-B03. Ordered by position for a stable,
        # walk-order sequence a surveyor can follow on the ground.
        members = sorted(zone.building_ids,
                         key=lambda bid: (to_shape(by_id[bid].centroid).y,
                                          to_shape(by_id[bid].centroid).x))
        for seq, bid in enumerate(members, start=1):
            b = by_id[bid]
            b.serving_zone_id = row.id
            b.building_code = f"{row.zone_code}-B{seq:02d}"

    summary = result.summary()
    audit_service.record(
        db, actor=user, entity_type="design_run", entity_id=run.id,
        action="run_design", project_id=project.id,
        changes={"rules": {"before": None, "after": result.rules_applied},
                 "summary": {"before": None, "after": summary}})
    db.commit()
    return {"design_run_id": str(run.id), **summary,
            "warnings": result.warnings}


def planning_point(building: Building, to_metric) -> Point:
    return transform(to_metric, to_shape(building.centroid))


def set_zone_drop_deployment(db: Session, user: User, project: Project,
                             zone_code: str, deployment: str | None) -> dict:
    """Bulk-set drop_deployment for every building served by a zone. The
    per-building flag is the source of truth — this is a convenience over it,
    so later per-building edits (e.g. field survey) simply override."""
    if deployment not in ("aerial", "underground", None):
        raise DesignError("deployment must be 'aerial', 'underground' or null.")
    run = db.scalar(select(DesignRun).where(
        DesignRun.project_id == project.id, DesignRun.is_current.is_(True)))
    if run is None:
        raise DesignError("Run a network design first.")
    zone = db.scalar(select(ServingZone).where(
        ServingZone.design_run_id == run.id,
        ServingZone.zone_code == zone_code))
    if zone is None:
        raise DesignError(f"No serving zone {zone_code} in the current design.")
    result = db.execute(update(Building)
                        .where(Building.serving_zone_id == zone.id)
                        .values(drop_deployment=deployment))
    audit_service.record(
        db, actor=user, entity_type="serving_zone", entity_id=zone.id,
        action="set_drop_deployment", project_id=project.id,
        changes={"deployment": {"before": None, "after": deployment},
                 "buildings": {"before": None, "after": result.rowcount}})
    db.commit()
    return {"zone_code": zone_code, "deployment": deployment,
            "buildings_updated": result.rowcount}


def current_design(db: Session, project_id: uuid.UUID) -> dict | None:
    run = db.scalar(select(DesignRun).where(
        DesignRun.project_id == project_id, DesignRun.is_current.is_(True)))
    if run is None:
        return None
    zones = list(db.scalars(select(ServingZone)
                            .where(ServingZone.design_run_id == run.id)
                            .order_by(ServingZone.zone_code)))
    fdhs = list(db.scalars(select(Fdh).where(Fdh.design_run_id == run.id)
                           .order_by(Fdh.fdh_code)))
    return {
        "design_run_id": str(run.id),
        "engine_version": run.engine_version,
        "ran_at": run.ran_at.isoformat(),
        "run_by": run.run_by,
        "rules": run.rules,
        "summary": run.summary,
        "warnings": run.warnings,
        "fdhs": [{"code": f.fdh_code, "premises": f.premises_count,
                  "fats": f.fat_count, "splitters": f.splitters,
                  "capacity": f.capacity, "utilisation_pct": float(f.utilisation_pct),
                  "reach_m": float(f.max_distribution_m)} for f in fdhs],
        "zones": [{
            "id": str(z.id), "zone_code": z.zone_code,
            "building_count": z.building_count, "premises_count": z.premises_count,
            "splitter_ratio": z.splitter_ratio, "usable_ports": z.usable_ports,
            "spare_ports": z.spare_ports,
            "utilisation_pct": float(z.utilisation_pct),
            "max_drop_m": float(z.max_drop_m), "avg_drop_m": float(z.avg_drop_m),
            "road_offset_m": (float(z.road_offset_m)
                              if z.road_offset_m is not None else None),
            "premises_assumed": z.premises_assumed,
            "warnings": z.warnings, "locked": z.locked,
        } for z in zones],
    }


def drops_geojson(db: Session, project: Project) -> dict:
    """Per-building drop routes for the current design, in EPSG:4326.

    Each served building's drop is routed along the corridor network — streets,
    service ways, footpaths and any traced pathway/fence line held as a Street —
    the same graph the feeder and distribution cables use, since aerial drops
    follow poles along those corridors and buried drops follow the same trenches.
    A lateral stub connects the FAT and the building to their nearest corridor
    node. The routed cable length (not straight-line) is measured and checked
    against the design's drop limit, so serviceability and drop-cable quantity
    are both confirmed building by building. Where the network can't reach a
    building it falls back to the straight line and flags it. Buildings the
    design left unassigned are returned as points, making gaps visible.
    """
    from collections import defaultdict

    from shapely.geometry import LineString, Point, mapping
    from app.domain.routing import StreetGraph
    run = db.scalar(select(DesignRun).where(
        DesignRun.project_id == project.id, DesignRun.is_current.is_(True)))
    if run is None:
        return {"type": "FeatureCollection", "features": [],
                "properties": {"drop_limit_m": None, "served": 0, "unserved": 0,
                               "over_limit": 0, "routed": 0, "straight": 0}}

    limit = float((run.rules or {}).get("max_drop_length_m", 150.0))
    to_metric = _transformer(STORAGE_EPSG, project.metric_crs_epsg).transform
    to_wgs = _transformer(project.metric_crs_epsg, STORAGE_EPSG).transform

    # Drops follow streets AND traced corridors (footpaths, fences, service
    # ways) — corridors feed only this graph, never the feeder/distribution
    # trenching. See app.db.models.corridor for why they are kept apart.
    from app.db.models.corridor import Corridor
    corridors = [transform(to_metric, to_shape(c.geom)) for c in db.scalars(
        select(Corridor).where(Corridor.project_id == project.id))]
    roads = [transform(to_metric, to_shape(s.geom)) for s in db.scalars(
        select(Street).where(Street.project_id == project.id))]
    network = roads + corridors
    graph = StreetGraph.from_roads(network) if network else None

    zones = {z.id: z for z in db.scalars(select(ServingZone)
             .where(ServingZone.design_run_id == run.id))}
    buildings = list(db.scalars(select(Building).where(
        Building.project_id == project.id, Building.excluded.is_(False))))

    features = []
    served = over = unserved = routed = straight = 0

    # Group served buildings by FAT so each FAT is searched ONCE. Routing a
    # separate Dijkstra per building (thousands) took minutes; a single-source
    # search per FAT (hundreds), reused across its cluster, returns in seconds.
    by_zone: dict = defaultdict(list)
    for b in buildings:
        zone = zones.get(b.serving_zone_id) if b.serving_zone_id else None
        if zone is None:
            unserved += 1
            features.append({
                "type": "Feature", "geometry": mapping(to_shape(b.centroid)),
                "properties": {"kind": "unserved", "code": b.building_code,
                               "serviceable": False}})
            continue
        by_zone[zone.id].append(b)

    for zone_id, members in by_zone.items():
        zone = zones[zone_id]
        fat = to_shape(zone.fat_point)
        fat_m = transform(to_metric, fat)
        dist = prev = fat_node = None
        stub_fat = 0.0
        if graph is not None:
            fat_node = graph.nearest_node(fat_m)
            dist, prev = graph.shortest_paths_from(fat_node)
            stub_fat = fat_m.distance(Point(graph.nodes[fat_node]))

        for b in members:
            cen_m = transform(to_metric, to_shape(b.centroid))
            line_m, drop_m, follows = None, None, False
            if graph is not None:
                line_m, d = graph.route_via(fat_m, fat_node, stub_fat,
                                            dist, prev, cen_m)
                if line_m is not None and d != float("inf"):
                    drop_m, follows = d, True
            if not follows:                   # no network / unreachable
                line_m = LineString([(fat_m.x, fat_m.y), (cen_m.x, cen_m.y)])
                drop_m = fat_m.distance(cen_m)

            drop_m = round(drop_m, 1)
            ok = drop_m <= limit
            served += 1
            routed += 1 if follows else 0
            straight += 0 if follows else 1
            if not ok:
                over += 1
            features.append({
                "type": "Feature",
                "geometry": mapping(transform(to_wgs, line_m)),
                "properties": {"kind": "drop", "fat": zone.zone_code,
                               "code": b.building_code, "drop_m": drop_m,
                               "routed": follows,
                               "premises_assumed": zone.premises_assumed,
                               "serviceable": ok}})

    return {"type": "FeatureCollection", "features": features,
            "properties": {"drop_limit_m": limit, "served": served,
                           "unserved": unserved, "over_limit": over,
                           "routed": routed, "straight": straight}}


def design_staleness(db: Session, project: Project) -> dict:
    """Is the current design behind the data it was built from?

    A design routes drops and sizes plant from the buildings and corridors as
    they were at run time. Any building drawn/moved/excluded or corridor traced
    afterwards means the map's drops and BOQ are stale. Postgres now() is
    constant within a transaction, so the reassignments made during the run
    share the run's ran_at exactly — a strict '>' flags only genuine later
    edits, never the run's own writes.
    """
    from sqlalchemy import func
    from app.db.models.corridor import Corridor
    run = db.scalar(select(DesignRun).where(
        DesignRun.project_id == project.id, DesignRun.is_current.is_(True)))
    if run is None:
        return {"has_design": False, "stale": False, "buildings_changed": 0,
                "corridors_changed": 0, "ran_at": None, "can_rerun": False}

    b_changed = db.scalar(select(func.count()).select_from(Building).where(
        Building.project_id == project.id,
        Building.updated_at > run.ran_at)) or 0
    c_changed = db.scalar(select(func.count()).select_from(Corridor).where(
        Corridor.project_id == project.id,
        Corridor.updated_at > run.ran_at)) or 0

    return {
        "has_design": True,
        "stale": bool(b_changed or c_changed),
        "buildings_changed": int(b_changed),
        "corridors_changed": int(c_changed),
        "ran_at": run.ran_at.isoformat(),
        # Only designs saved with the full rule set can be reproduced exactly.
        "can_rerun": "noc_anchored" in (run.rules or {}),
    }


def rerun_design(db: Session, user: User, project: Project) -> dict:
    """Re-run the design reusing the current run's saved settings, so drops and
    BOQ catch up with edited buildings/corridors without the user re-entering
    rules. Refuses on legacy runs that predate full-rule storage."""
    from shapely.geometry import Point
    from shapely.ops import transform as _tf
    from app.domain.planning.rules import DesignRules
    from app.services.pilot_service import NOC_LAT, NOC_LON

    run = db.scalar(select(DesignRun).where(
        DesignRun.project_id == project.id, DesignRun.is_current.is_(True)))
    if run is None:
        raise DesignError("Run a network design first.")
    saved = run.rules or {}
    if "noc_anchored" not in saved:
        raise DesignError(
            "This design predates one-click re-run. Re-run it once from the "
            "Design panel with your settings; future re-runs will be one click.")

    anchor = None
    if saved.get("noc_anchored"):
        to_metric = _transformer(STORAGE_EPSG, project.metric_crs_epsg).transform
        p = _tf(to_metric, Point(NOC_LON, NOC_LAT))
        anchor = (p.x, p.y)

    rules = DesignRules(
        split_stage=saved.get("split_stage", "single"),
        fdh_split_ratio=saved.get("fdh_split_ratio", 32),
        fat_split_ratio=saved.get("fat_split_ratio", 1),
        fat_port_count=saved.get("fat_port_count", 16),
        spare_port_ratio=saved.get("spare_port_ratio", 0.20),
        max_drop_length_m=saved.get("max_drop_length_m", 150.0),
        min_premises_per_fat=saved.get("min_premises_per_fat", 4),
        assumed_premises_per_building=saved.get("assumed_premises_per_building", 1),
        max_fat_road_offset_m=saved.get("max_fat_road_offset_m", 25.0),
        max_fdh_distribution_m=saved.get("max_fdh_distribution_m", 2000.0),
        noc_anchor=anchor)
    return run_design(db, user, project, rules)


def design_geojson(db: Session, project_id: uuid.UUID) -> dict:
    from shapely.geometry import mapping
    run = db.scalar(select(DesignRun).where(
        DesignRun.project_id == project_id, DesignRun.is_current.is_(True)))
    if run is None:
        return {"type": "FeatureCollection", "features": []}

    features = []
    for f in db.scalars(select(Fdh).where(Fdh.design_run_id == run.id)):
        features.append({"type": "Feature", "geometry": mapping(to_shape(f.point)),
                         "properties": {"kind": "fdh", "code": f.fdh_code,
                                        "fdh_id": str(f.id),
                                        "premises": f.premises_count,
                                        "fats": f.fat_count,
                                        "splitters": f.splitters,
                                        "capacity": f.capacity,
                                        "utilisation": float(f.utilisation_pct),
                                        "reach_m": float(f.max_distribution_m)}})
    for z in db.scalars(select(ServingZone)
                        .where(ServingZone.design_run_id == run.id)):
        props = {
            "zone_code": z.zone_code, "zone_id": str(z.id),
            "premises": z.premises_count,
            "buildings": z.building_count,
            "utilisation": float(z.utilisation_pct),
            "spare_ports": z.spare_ports,
            "max_drop_m": float(z.max_drop_m),
            "premises_assumed": z.premises_assumed,
            "has_warning": bool(z.warnings),
        }
        if z.extent is not None:
            features.append({"type": "Feature", "geometry": mapping(to_shape(z.extent)),
                             "properties": {**props, "kind": "extent"}})
        features.append({"type": "Feature", "geometry": mapping(to_shape(z.fat_point)),
                         "properties": {**props, "kind": "fat"}})
    return {"type": "FeatureCollection", "features": features}
