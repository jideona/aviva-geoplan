"""Assemble the buildable pilot from the current design."""
from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from shapely.ops import transform
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.design import DesignRun, ServingZone
from app.db.models.parcel import Parcel
from app.db.models.project import Project
from app.domain.connectorised import DemandPoint, fit, stock_from_lines
from app.domain.crs import STORAGE_EPSG, _transformer
from app.domain.pilot import FatDemand, build_pilot
from app.services import inventory_service
from app.services.connectorised_service import DEFAULT_STOCK, DUCT_SINUOSITY

# NOC — Boya Place, Ameh Ebute Street (from the Aviva HLD).
NOC_LON, NOC_LAT = 7.43565602, 9.04977333
# Placeholder figures — used only when the organisation hasn't uploaded a real
# stock sheet yet (see inventory_service). Never silently trusted for a real
# procurement decision; build() appends a warning whenever these are in use.
SPLITTER_STOCK = {32: 18, 8: 78, 4: 20}


class PilotError(ValueError):
    """Message is safe to show the user."""


def build(db: Session, project: Project, olt_pon_ports: int = 16) -> dict:
    run = db.scalar(select(DesignRun).where(
        DesignRun.project_id == project.id, DesignRun.is_current.is_(True)))
    if run is None:
        raise PilotError("Run a network design first.")
    zones = list(db.scalars(select(ServingZone)
                            .where(ServingZone.design_run_id == run.id)))
    if not zones:
        raise PilotError("The current design has no FATs.")

    to_metric = _transformer(STORAGE_EPSG, project.metric_crs_epsg).transform
    noc = transform(to_metric, Point(NOC_LON, NOC_LAT))

    demand = []
    for z in zones:
        fat = transform(to_metric, to_shape(z.fat_point))
        dist = noc.distance(fat) * DUCT_SINUOSITY
        demand.append(FatDemand(z.zone_code, dist, z.premises_count))

    # Real uploaded stock wins when present; otherwise fall back to the
    # placeholder constants so an org that hasn't uploaded a stock sheet yet
    # doesn't get a design that reports everything as a shortfall.
    stock_warnings: list[str] = []
    splitter_stock = inventory_service.stock_map_for_splitters(db, project.organisation_id)
    if not splitter_stock:
        splitter_stock = dict(SPLITTER_STOCK)
        stock_warnings.append(
            "No splitter stock uploaded for this organisation — splitter "
            "req/stock/buy figures use placeholder assumptions, not your "
            "real warehouse stock. Upload a stock sheet for real figures.")
    conn_stock_lines = inventory_service.stock_lines_for_connectorised(
        db, project.organisation_id)
    if not conn_stock_lines:
        conn_stock_lines = DEFAULT_STOCK
        stock_warnings.append(
            "No connectorised FAT cable stock uploaded — the connectorised "
            "fit uses placeholder assumptions, not your real warehouse stock.")

    # Connectorised fit against the near-NOC demand (route distance from NOC).
    conn_demand = [DemandPoint(d.fat_code, d.distance_from_noc_m, d.premises)
                   for d in demand]
    conn_fit = fit(conn_demand, stock_from_lines(conn_stock_lines))

    plan = build_pilot(demand, splitter_stock, conn_fit, olt_pon_ports)

    return {
        "project": project.name,
        "olt_pon_ports": plan.olt_pon_ports,
        "phase1_premises": plan.phase1_premises,
        "phase2_premises": plan.phase2_premises,
        "total_premises": plan.total_premises,
        "unserved_fats": plan.unserved_fats,
        "equipment": plan.equipment,
        "warnings": plan.warnings + stock_warnings,
        "phase1_fats": [f.__dict__ for f in plan.phase1_fats],
        "phase2_fats": [f.__dict__ for f in plan.phase2_fats],
    }
