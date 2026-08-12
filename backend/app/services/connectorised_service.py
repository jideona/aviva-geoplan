"""Fit the current design to pre-connectorised underground stock."""
import uuid

from geoalchemy2.shape import to_shape
from shapely.ops import transform
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.design import DesignRun, Fdh, ServingZone
from app.db.models.street import Street
from app.domain.routing import StreetGraph, route_distribution
from app.db.models.project import Project
from app.domain.connectorised import DemandPoint, fit, stock_from_lines
from app.domain.equipment_envelope import envelope
from app.domain.crs import STORAGE_EPSG, _transformer
from app.services import inventory_service

# Aviva pre-connectorised underground stock — placeholder, used only when the
# organisation hasn't uploaded a real stock sheet (see inventory_service.
# stock_lines_for_connectorised, now the primary source).
DEFAULT_STOCK = [
    ("4way", 4, 200, 1), ("4way", 4, 300, 2),
    ("8way", 8, 50, 1), ("8way", 8, 150, 1), ("8way", 8, 250, 4), ("8way", 8, 350, 2),
    ("12way", 12, 100, 4), ("12way", 12, 150, 1), ("12way", 12, 250, 3),
    ("12way", 12, 350, 3),
    ("novux_12pt", 0, 250, 8), ("novux_12pt", 0, 350, 4),
]

# Underground routes follow ducts, not straight lines. This factor lifts the
# straight-line FDH-to-FAT distance toward the real trench length until street
# routing replaces it with the measured value.
DUCT_SINUOSITY = 1.35


class ConnectorisedError(ValueError):
    """Message is safe to show the user."""


def fit_report(db: Session, project: Project) -> dict:
    run = db.scalar(select(DesignRun).where(
        DesignRun.project_id == project.id, DesignRun.is_current.is_(True)))
    if run is None:
        raise ConnectorisedError("Run a network design first.")

    fdhs = {f.id: to_shape(f.point) for f in db.scalars(
        select(Fdh).where(Fdh.design_run_id == run.id))}
    zones = list(db.scalars(select(ServingZone)
                            .where(ServingZone.design_run_id == run.id)))
    if not zones:
        raise ConnectorisedError("The current design has no FATs.")

    to_metric = _transformer(STORAGE_EPSG, project.metric_crs_epsg).transform
    metric_fdh = {fid: transform(to_metric, g) for fid, g in fdhs.items()}

    # Real street routes, not straight-line x sinuosity — a pre-connectorised
    # cable either reaches along the duct or it does not, and only the routed
    # distance answers that.
    roads = [transform(to_metric, to_shape(s.geom))
             for s in db.scalars(select(Street).where(Street.project_id == project.id))]
    graph = StreetGraph.from_roads(roads) if roads else None

    routed_distance: dict[str, float] = {}
    if graph is not None:
        by_fdh: dict = {}
        for z in zones:
            if z.fdh_id in metric_fdh:
                by_fdh.setdefault(z.fdh_id, []).append(
                    (z.zone_code, transform(to_metric, to_shape(z.fat_point))))
        for fid, fats in by_fdh.items():
            tree = route_distribution(graph, metric_fdh[fid], fats)
            for leg in tree.legs:
                routed_distance[leg.to_code] = leg.length_m

    demand = []
    no_fdh = 0
    for z in zones:
        fat = transform(to_metric, to_shape(z.fat_point))
        parent = metric_fdh.get(z.fdh_id)
        if parent is None:
            no_fdh += 1
            continue
        # Prefer the routed distance; fall back to the estimate only where the
        # route could not be computed.
        dist = routed_distance.get(z.zone_code, fat.distance(parent) * DUCT_SINUOSITY)
        demand.append(DemandPoint(z.zone_code, dist, z.premises_count))

    lines = inventory_service.stock_lines_for_connectorised(db, project.organisation_id)
    using_placeholder = not lines
    if using_placeholder:
        lines = DEFAULT_STOCK
    stock = stock_from_lines(lines)
    result = fit(demand, stock)
    summary = result.summary()

    fat_terminals = sum(q for k, _, _, q in lines if k != "novux_12pt")
    total_ports = sum(p * q for k, p, _, q in lines if k != "novux_12pt")

    return {
        "project": project.name,
        "stock": {
            "fat_terminals": fat_terminals,
            "total_drop_ports": total_ports,
            "feeder_cables": sum(q for k, _, _, q in lines
                                 if k == "novux_12pt"),
            "duct_sinuosity_assumed": DUCT_SINUOSITY,
            "placeholder_figures": using_placeholder,
        },
        "achievable": summary,
        "assignments": [{
            "fat_code": a.fat_code, "route_m": a.route_distance_m,
            "premises": a.premises, "cable": f"{a.cable.kind} {a.cable.length_m}m",
            "cable_ports": a.cable.ports, "slack_m": a.slack_m,
            "spare_ports": a.spare_ports,
        } for a in sorted(result.assignments, key=lambda x: -x.route_distance_m)],
        "unserved": [{
            "fat_code": u.fat_code, "route_m": u.route_distance_m,
            "premises": u.premises, "reason": u.reason,
        } for u in result.unserved[:50]],
        "note": (
            "Route distance is straight-line FDH-to-FAT scaled by an assumed "
            f"{DUCT_SINUOSITY}x duct factor; street routing will replace it with "
            "the measured trench length. Fixed-length cables (50-350 m) require "
            "FATs within roughly 260 m route of a feed point — the binding "
            "constraint on this stock, not port count."
            + (" PLACEHOLDER STOCK — no connectorised cable uploaded for this "
               "organisation; upload a stock sheet for real figures."
               if using_placeholder else "")
        ),
    }


# Splitter stock placeholder — used only when no real stock has been
# uploaded for the organisation (see inventory_service.stock_map_for_splitters).
SPLITTER_STOCK = {32: 18, 8: 78, 4: 20}


def combined_envelope(db: Session | None = None,
                      organisation_id: uuid.UUID | None = None) -> dict:
    """What the full equipment set — splitters plus connectorised terminals —
    can serve, phased and honest about the two being complementary.

    Falls back to placeholder stock if db/organisation_id aren't supplied, or
    if the organisation hasn't uploaded a real stock sheet — kept optional so
    existing callers that don't pass them still work.
    """
    lines = DEFAULT_STOCK
    splitter_stock = SPLITTER_STOCK
    if db is not None and organisation_id is not None:
        real_lines = inventory_service.stock_lines_for_connectorised(db, organisation_id)
        if real_lines:
            lines = real_lines
        real_splitters = inventory_service.stock_map_for_splitters(db, organisation_id)
        if real_splitters:
            splitter_stock = real_splitters
    ports = sum(p * q for k, p, _, q in lines if k != "novux_12pt")
    terminals = sum(q for k, _, _, q in lines if k != "novux_12pt")
    return envelope(splitter_stock, ports, terminals, olt_pon_ports=16)
