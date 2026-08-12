"""Assemble the FAT coverage & density report from project data."""
import uuid

from geoalchemy2.shape import to_shape
from shapely.ops import transform
from shapely.strtree import STRtree
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.building import Building
from app.db.models.design import DesignRun, ServingZone
from app.db.models.parcel import Parcel
from app.db.models.project import Project
from app.domain.coverage import (BuildingAssessment, FatCoverage, assess_building,
                                 summarise_fat)
from app.domain.crs import STORAGE_EPSG, _transformer


class CoverageError(ValueError):
    """Message is safe to show the user."""


def _similar_neighbour_count(metric_geoms: dict, bid: str, area: float,
                             tree: STRtree, geom_ids: list[str],
                             tol: float = 0.30) -> int:
    """Adjacent footprints of similar size — the terrace signal."""
    g = metric_geoms[bid]
    hits = tree.query(g.buffer(6.0))   # within 6 m counts as adjacent
    n = 0
    for i in hits:
        other = geom_ids[int(i)]
        if other == bid:
            continue
        oa = metric_geoms[other].area
        if area and abs(oa - area) / area <= tol:
            n += 1
    return n


def build_report(db: Session, project: Project) -> dict:
    run = db.scalar(select(DesignRun).where(
        DesignRun.project_id == project.id, DesignRun.is_current.is_(True)))
    if run is None:
        raise CoverageError("Run a network design first — coverage is reported "
                            "per FAT serving zone.")

    zones = list(db.scalars(select(ServingZone)
                            .where(ServingZone.design_run_id == run.id)))
    if not zones:
        raise CoverageError("The current design has no serving zones.")

    to_metric = _transformer(STORAGE_EPSG, project.metric_crs_epsg).transform

    # Parcels with a surveyed unit count give confirmed data. Spread the estate
    # total across its buildings — the survey counted the estate, not each door.
    parcels = list(db.scalars(select(Parcel).where(Parcel.project_id == project.id)))
    parcel_units_per_building: dict[uuid.UUID, float] = {}
    parcel_name: dict[uuid.UUID, str] = {}
    for p in parcels:
        parcel_name[p.id] = p.name
        units = p.observed_units or p.declared_units
        if units and p.building_count:
            parcel_units_per_building[p.id] = units / p.building_count

    buildings = list(db.scalars(select(Building)
                                .where(Building.project_id == project.id,
                                       Building.serving_zone_id.isnot(None))))
    metric_geoms = {str(b.id): transform(to_metric, to_shape(b.geom))
                    for b in buildings}
    geom_ids = list(metric_geoms)
    tree = STRtree([metric_geoms[i] for i in geom_ids])

    by_zone: dict[uuid.UUID, list[Building]] = {}
    for b in buildings:
        by_zone.setdefault(b.serving_zone_id, []).append(b)

    reports: list[FatCoverage] = []
    for zone in zones:
        members = by_zone.get(zone.id, [])
        assessments: list[BuildingAssessment] = []
        estates: set[str] = set()
        for b in members:
            bid = str(b.id)
            area = float(b.footprint_area_sqm)
            confirmed = None
            pname = None
            if b.parcel_id and b.parcel_id in parcel_units_per_building:
                # Round the per-building share to a whole unit.
                confirmed = max(1, round(parcel_units_per_building[b.parcel_id]))
                pname = parcel_name.get(b.parcel_id)
                estates.add(pname)
            elif b.units_surveyed:
                confirmed = b.units_surveyed
            neighbours = _similar_neighbour_count(metric_geoms, bid, area,
                                                  tree, geom_ids)
            assessments.append(assess_building(bid, area, neighbours, confirmed, pname))

        zone_area = _zone_area(zone, to_metric)
        reports.append(summarise_fat(zone.zone_code, zone_area, assessments,
                                     list(estates)))

    return _shape_output(project, run, reports)


def _zone_area(zone: ServingZone, to_metric) -> float:
    if zone.extent is not None:
        return transform(to_metric, to_shape(zone.extent)).area
    return 0.0


def _shape_output(project: Project, run: DesignRun,
                  reports: list[FatCoverage]) -> dict:
    total_confirmed = sum(r.confirmed_units for r in reports)
    total_est = sum(r.estimated_units_likely for r in reports)
    confirmed_b = sum(r.confirmed_buildings for r in reports)
    estimated_b = sum(r.estimated_buildings for r in reports)

    return {
        "project": project.name,
        "design_run_id": str(run.id),
        "engine_version": run.engine_version,
        "fat_count": len(reports),
        "totals": {
            "buildings": confirmed_b + estimated_b,
            "confirmed_buildings": confirmed_b,
            "estimated_buildings": estimated_b,
            "confirmed_units": total_confirmed,
            "estimated_units_likely": total_est,
            "estimated_units_low": sum(r.estimated_units_low for r in reports),
            "estimated_units_high": sum(r.estimated_units_high for r in reports),
            "total_units_likely": total_confirmed + total_est,
        },
        "note": (
            "Confirmed units come from surveyed parcels; estimated units are "
            "inferred from footprint geometry and are labelled per FAT. The two "
            "are reported separately and never combined into a single "
            "unqualified figure."
        ),
        "fats": [{
            "fat_code": r.fat_code,
            "area_sqm": r.area_sqm,
            "density_per_ha": r.property_density_per_ha,
            "coverage_quality": r.coverage_quality,
            "buildings": r.building_count,
            "confirmed_buildings": r.confirmed_buildings,
            "estimated_buildings": r.estimated_buildings,
            "confirmed_units": r.confirmed_units,
            "estimated_units_likely": r.estimated_units_likely,
            "estimated_units_range": [r.estimated_units_low, r.estimated_units_high],
            "total_units_likely": r.total_units_likely,
            "overall_confidence": r.overall_confidence,
            "estates_served": r.estates_served,
            "breakdown": [{
                "type": b.property_type.value,
                "buildings": b.buildings,
                "confirmed_buildings": b.confirmed_buildings,
                "estimated_buildings": b.estimated_buildings,
                "units_likely": b.units_likely,
                "units_range": [b.units_low, b.units_high],
                "confidence": b.confidence,
            } for b in r.breakdown],
        } for r in reports],
    }
