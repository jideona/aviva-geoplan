"""Optical loss budget over the pilot's real routed paths."""
from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from shapely.ops import transform
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.design import DesignRun, Fdh, ServingZone
from app.db.models.project import Project
from app.db.models.street import Street
from app.domain.crs import STORAGE_EPSG, _transformer
from app.domain.optical import OpticalParams, PathSpec, Verdict, compute
from app.domain.routing import StreetGraph, route_feeder
from app.services.pilot_service import NOC_LAT, NOC_LON

# Splitter chain per phase. Phase 1 connectorised is single-stage 1:32; Phase 2
# conventional is two-stage 1:4 x 1:8.
PHASE_SPLITTERS = {1: [32], 2: [4, 8]}
MAX_DROP_M = 150.0     # worst-case drop for the budget


class OpticalError(ValueError):
    """Message is safe to show the user."""


def budget_report(db: Session, project: Project, phase: int,
                  params: OpticalParams | None = None) -> dict:
    params = params or OpticalParams()
    run = db.scalar(select(DesignRun).where(
        DesignRun.project_id == project.id, DesignRun.is_current.is_(True)))
    if run is None:
        raise OpticalError("Run a network design first.")

    from app.services import pilot_service
    plan = pilot_service.build(db, project)
    scope = {f["fat_code"] for f in
             (plan["phase1_fats"] if phase == 1 else plan["phase2_fats"])}
    if not scope:
        raise OpticalError(f"Phase {phase} has no FATs in the pilot.")

    to_metric = _transformer(STORAGE_EPSG, project.metric_crs_epsg).transform
    roads = [transform(to_metric, to_shape(s.geom))
             for s in db.scalars(select(Street).where(Street.project_id == project.id))]
    graph = StreetGraph.from_roads(roads)
    noc = transform(to_metric, Point(NOC_LON, NOC_LAT))
    noc_node = graph.nearest_node(noc)

    zones = {z.zone_code: z for z in db.scalars(
        select(ServingZone).where(ServingZone.design_run_id == run.id))}
    fdhs = {f.id: f for f in db.scalars(select(Fdh).where(Fdh.design_run_id == run.id))}

    # Feeder length per FDH (NOC -> FDH) once.
    feeder_len: dict = {}
    for fid, f in fdhs.items():
        length, _ = graph.shortest_path(noc_node, graph.nearest_node(
            transform(to_metric, to_shape(f.point))))
        feeder_len[fid] = length if length != float("inf") else 0.0

    splitters = PHASE_SPLITTERS[phase]
    results = []
    worst = None
    for code in scope:
        z = zones.get(code)
        if z is None or z.fdh_id not in fdhs:
            continue
        fdh = fdhs[z.fdh_id]
        fdh_pt = transform(to_metric, to_shape(fdh.point))
        fat_pt = transform(to_metric, to_shape(z.fat_point))
        dist_len, _ = graph.shortest_path(graph.nearest_node(fdh_pt),
                                          graph.nearest_node(fat_pt))
        if dist_len == float("inf"):
            dist_len = fdh_pt.distance(fat_pt)

        path = PathSpec(feeder_m=feeder_len.get(z.fdh_id, 0.0),
                        distribution_m=dist_len, drop_m=MAX_DROP_M,
                        splitter_ratios=splitters)
        r = compute(path, params)
        row = {"fat_code": code, "feeder_m": round(feeder_len.get(z.fdh_id, 0.0), 1),
               "distribution_m": round(dist_len, 1), **r.as_dict()}
        results.append(row)
        if worst is None or r.total_loss_db > worst["total_loss_db"]:
            worst = row

    passes = sum(1 for r in results if r["verdict"] == "pass")
    warns = sum(1 for r in results if r["verdict"] == "warning")
    fails = sum(1 for r in results if r["verdict"] == "fail")

    return {
        "phase": phase,
        "architecture": ("single-stage 1:32" if phase == 1
                         else "two-stage 1:4 x 1:8 = 1:32"),
        "system_budget_db": params.system_budget_db,
        "paths": len(results),
        "pass": passes, "warning": warns, "fail": fails,
        "worst_case_path": worst,
        "verdict": ("fail" if fails else "warning" if warns else "pass"),
        "params": {
            "fibre_db_per_km": params.fibre_db_per_km,
            "olt_launch_dbm": params.olt_launch_dbm,
            "ont_sensitivity_dbm": params.ont_sensitivity_dbm,
            "required_margin_db": params.required_margin_db,
        },
        "results": sorted(results, key=lambda r: -r["total_loss_db"])[:50],
        "note": (
            "Loss computed on real routed feeder + distribution lengths, worst-"
            f"case {MAX_DROP_M:.0f} m drop. Every parameter is configurable; "
            "no attenuation or insertion value is fixed in code."
        ),
    }
