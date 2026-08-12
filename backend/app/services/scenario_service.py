"""Design scenario comparison — run alternative rule sets in memory and report
the quantities that drive the BOQ, side by side. Nothing is persisted: the
current design, zones, FDH placements and building codes are untouched.

Each scenario runs the same planning engine as a real design run, then routes
the in-memory result along the street graph exactly the way the BOQ does, so
FAT/FDH counts, trench and cable figures are directly comparable with the
committed design's pack.
"""
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.building import Building
from app.db.models.project import Project
from app.db.models.street import Street
from app.domain.crs import STORAGE_EPSG, _transformer
from app.domain.planning.engine import PlanningError, plan
from app.domain.planning.model import PlanningBuilding, PlanningRoad
from app.domain.planning.rules import DesignRules
from app.domain.routing import (StreetGraph, chamber_schedule,
                                route_distribution, route_feeder)
from app.services.pilot_service import NOC_LAT, NOC_LON
from app.services.routing_service import (CONTINGENCY, JOINTING, SLACK,
                                          WASTAGE)
from geoalchemy2.shape import to_shape
from shapely.ops import transform

DROP_SLACK = 1.10   # matches the design pack's drop estimate allowance


class ScenarioError(ValueError):
    """Message is safe to show the user."""


def _with_allowances(measured_m: float) -> float:
    return round(measured_m * (1 + SLACK + JOINTING + WASTAGE + CONTINGENCY), 1)


def compare(db: Session, project: Project, scenarios: list[dict]) -> dict:
    """scenarios: list of dicts of RunRequest fields plus 'label'."""
    if not 1 <= len(scenarios) <= 3:
        raise ScenarioError("Compare between one and three scenarios.")

    to_metric = _transformer(STORAGE_EPSG, project.metric_crs_epsg).transform

    buildings = list(db.scalars(
        select(Building).where(Building.project_id == project.id,
                               Building.excluded.is_(False))))
    if not buildings:
        raise ScenarioError("Import buildings before running scenarios.")
    streets = list(db.scalars(
        select(Street).where(Street.project_id == project.id)))
    if not streets:
        raise ScenarioError("Import roads before running scenarios.")

    # Load geometry once; premises assumption is applied per scenario.
    base = []
    for b in buildings:
        pt = transform(to_metric, to_shape(b.centroid))
        if b.units_surveyed:
            premises, assumed = b.units_surveyed, False
        elif b.premises_estimated:
            premises, assumed = b.premises_estimated, False
        else:
            premises, assumed = None, True
        base.append((str(b.id), pt, premises, assumed,
                     str(b.street_id) if b.street_id else None,
                     str(b.parcel_id) if b.parcel_id else None))

    roads = [PlanningRoad(id=str(s.id),
                          geometry=transform(to_metric, to_shape(s.geom)),
                          road_class=s.road_class) for s in streets]
    graph = StreetGraph.from_roads([r.geometry for r in roads])
    noc = transform(to_metric, Point(NOC_LON, NOC_LAT))

    out = []
    for sc in scenarios:
        sc = dict(sc)
        label = sc.pop("label", "") or f"Scenario {len(out) + 1}"
        anchored = sc.pop("noc_anchored", False)
        try:
            rules = DesignRules(
                noc_anchor=(noc.x, noc.y) if anchored else None, **sc)
        except TypeError as exc:
            raise ScenarioError(f"{label}: unknown rule field ({exc})") from exc

        pbs = [PlanningBuilding(
            id=bid, point=pt,
            premises=(premises if premises is not None
                      else rules.assumed_premises_per_building),
            premises_is_assumed=assumed, code=None,
            street_id=sid, group_id=gid)
            for bid, pt, premises, assumed, sid, gid in base]

        try:
            result = plan(pbs, roads, rules)
        except PlanningError as exc:
            out.append({"label": label, "error": str(exc), "rules": sc})
            continue

        zones_by_suffix = {z.code_suffix: z for z in result.zones}
        trench = leg_total = lateral = 0.0
        feeder_fdhs, all_fats = [], []
        unreachable = 0
        for f in result.fdhs:
            fats = [(sfx, zones_by_suffix[sfx].fat_point)
                    for sfx in f.fat_codes if sfx in zones_by_suffix]
            if not fats:
                continue
            tree = route_distribution(graph, f.point, fats)
            trench += tree.trench_length_m
            leg_total += tree.total_leg_length_m
            unreachable += len(tree.unreachable)
            feeder_fdhs.append((f.code_suffix, f.point))
            all_fats.extend(fats)
            node = graph.nodes[graph.nearest_node(f.point)]
            lateral += f.point.distance(Point(node))
            for _, fp in fats:
                n = graph.nodes[graph.nearest_node(fp)]
                lateral += fp.distance(Point(n))

        feeder = route_feeder(graph, noc, feeder_fdhs)
        feeder_len = sum(l.length_m for l in feeder)
        trench_total = round(trench + feeder_len + lateral, 1)
        chambers = chamber_schedule(noc, feeder_fdhs, all_fats, trench_total)

        drop_cable = round(sum(z.avg_drop_m * len(z.building_ids)
                               for z in result.zones) * DROP_SLACK, 1)
        served_buildings = sum(len(z.building_ids) for z in result.zones)
        served_premises = sum(z.premises for z in result.zones)
        splitters = sum(f.splitters for f in result.fdhs)
        utilisation = (served_premises / (len(result.zones) * rules.usable_ports)
                       * 100 if result.zones and rules.usable_ports else 0)

        out.append({
            "label": label,
            "rules": {
                "fat_port_count": rules.fat_port_count,
                "spare_port_ratio": rules.spare_port_ratio,
                "usable_ports": rules.usable_ports,
                "max_drop_length_m": rules.max_drop_length_m,
                "min_premises_per_fat": rules.min_premises_per_fat,
                "max_fdh_distribution_m": rules.max_fdh_distribution_m,
                "noc_anchored": anchored,
            },
            "fats": len(result.zones),
            "fdhs": len(result.fdhs),
            "splitters": splitters,
            "served_buildings": served_buildings,
            "served_premises": served_premises,
            "unassigned_buildings": len(result.unassigned_building_ids),
            "avg_fat_utilisation_pct": round(utilisation, 1),
            "trench_m": trench_total,
            "feeder_cable_m": _with_allowances(feeder_len),
            "distribution_cable_m": _with_allowances(trench),
            "drop_cable_m": drop_cable,
            "duct_sharing_saving_m": round(leg_total - trench, 1),
            "chambers": chambers,
            "fats_unreachable": unreachable,
            "warnings": len(result.warnings),
        })

    return {"scenarios": out,
            "note": ("Dry-run only — the committed design is untouched. "
                     "Quantities use the same street routing and allowances "
                     "as the design pack; drop cable is buildings x avg drop "
                     "x 1.1.")}
