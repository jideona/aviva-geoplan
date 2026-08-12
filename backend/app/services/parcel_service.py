"""Import estate perimeters and link them to buildings and observed units."""
import uuid

from geoalchemy2.shape import from_shape, to_shape
from shapely.ops import transform
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.building import Building
from app.db.models.parcel import Parcel
from app.db.models.project import Project
from app.db.models.survey_data import PremisesObservation
from app.db.models.user import User
from app.domain.crs import STORAGE_EPSG, _transformer
from app.domain.licences import LicenceClass
from app.domain.name_matching import is_possible, similarity
from app.domain.parcels import (ParcelParseError, looks_unnamed, parse_markers,
                                parse_parcels)
from app.services import audit_service, boundary_service, import_service


class ParcelError(ValueError):
    """Message is safe to show the user."""


def import_perimeters(db: Session, user: User, project: Project,
                      filename: str, data: bytes) -> dict:
    boundary = boundary_service.get_current(db, project.id)
    if boundary is None:
        raise ParcelError("Upload a project boundary before importing parcels.")
    clip = to_shape(boundary.geom)
    to_metric = _transformer(STORAGE_EPSG, project.metric_crs_epsg).transform

    try:
        parsed = parse_parcels(filename, data)
    except ParcelParseError as exc:
        raise ParcelError(str(exc)) from exc

    src = import_service._get_or_create_source(
        db, "Aviva estate perimeter survey (KML)", "field_survey",
        "Proprietary — Aviva Networx", LicenceClass.OWNED.value)

    existing = {p.raw_name: p for p in db.scalars(
        select(Parcel).where(Parcel.project_id == project.id))}
    seq = db.scalar(select(func.count()).select_from(Parcel)
                    .where(Parcel.project_id == project.id)) or 0

    created = updated = outside = 0
    for item in parsed:
        if not clip.intersects(item.geometry):
            outside += 1
            continue
        metric = transform(to_metric, item.geometry)
        row = existing.get(item.raw_name)
        if row is None:
            seq += 1
            row = Parcel(project_id=project.id,
                         parcel_code=f"{project.code_prefix}-PCL-{seq:03d}",
                         data_source_id=src.id)
            db.add(row)
            created += 1
        else:
            updated += 1
        row.name = item.name
        row.raw_name = item.raw_name
        row.survey_code = item.survey_code
        row.declared_units = item.declared_units
        row.geom = from_shape(item.geometry, srid=4326)
        row.area_sqm = round(metric.area, 2)
        row.perimeter_m = round(metric.length, 2)
        row.licence_class = LicenceClass.OWNED.value
        row.verification_state = "field_observed"

    db.flush()
    linked = _link_buildings(db, project)
    result = {"created": created, "updated": updated,
              "outside_boundary": outside, "buildings_linked": linked}

    audit_service.record(
        db, actor=user, entity_type="parcel", entity_id=None, action="import",
        project_id=project.id,
        changes={"file": {"before": None, "after": filename},
                 "result": {"before": None, "after": result}})
    db.commit()
    return result


def import_markers(db: Session, user: User, project: Project,
                   filename: str, data: bytes) -> dict:
    """Count points dropped on each surveyed building, tallied per parcel."""
    try:
        markers = parse_markers(filename, data)
    except ParcelParseError as exc:
        raise ParcelError(str(exc)) from exc

    parcels = list(db.scalars(select(Parcel).where(Parcel.project_id == project.id)))
    if not parcels:
        raise ParcelError("Import estate perimeters before the count markers.")

    shapes = [(p, to_shape(p.geom)) for p in parcels]
    tally: dict[uuid.UUID, int] = {}
    orphaned = 0
    for marker in markers:
        hit = next((p for p, g in shapes if g.contains(marker.geometry)), None)
        if hit is None:
            orphaned += 1
            continue
        tally[hit.id] = tally.get(hit.id, 0) + 1

    for parcel in parcels:
        parcel.marker_count = tally.get(parcel.id, 0)

    result = {"markers": len(markers), "matched": len(markers) - orphaned,
              "orphaned": orphaned, "parcels_with_markers": len(tally)}
    audit_service.record(
        db, actor=user, entity_type="parcel", entity_id=None,
        action="import_markers", project_id=project.id,
        changes={"file": {"before": None, "after": filename},
                 "result": {"before": None, "after": result}})
    db.commit()
    return result


def _link_buildings(db: Session, project: Project) -> int:
    """Assign each building to the parcel containing its centroid."""
    parcels = [(p, to_shape(p.geom)) for p in db.scalars(
        select(Parcel).where(Parcel.project_id == project.id))]
    if not parcels:
        return 0
    counts: dict[uuid.UUID, int] = {}
    linked = 0
    for b in db.scalars(select(Building).where(Building.project_id == project.id)):
        centroid = to_shape(b.centroid)
        hit = next((p for p, g in parcels if g.contains(centroid)), None)
        b.parcel_id = hit.id if hit else None
        if hit:
            counts[hit.id] = counts.get(hit.id, 0) + 1
            linked += 1
    for parcel, _ in parcels:
        parcel.building_count = counts.get(parcel.id, 0)
    db.flush()
    return linked


def attach_observed_units(db: Session, user: User, project: Project) -> dict:
    """Match workbook estate counts to parcels by name, and record the units.

    Where the perimeter survey and the workbook disagree on building count,
    both figures are kept. A discrepancy is information, not an error to
    silently resolve.
    """
    parcels = list(db.scalars(select(Parcel).where(Parcel.project_id == project.id)))
    observations = list(db.scalars(select(PremisesObservation)
                                   .where(PremisesObservation.project_id == project.id)))
    if not parcels or not observations:
        return {"matched": 0, "reason": "Need both perimeters and observations."}

    totals: dict[str, dict] = {}
    for row in observations:
        t = totals.setdefault(row.estate_name, {"buildings": 0, "units": 0})
        t["buildings"] += row.building_count
        t["units"] += row.building_count * row.units_per_building

    matched, disagreements = 0, []
    for parcel in parcels:
        best, score = None, 0.0
        for name in totals:
            s = similarity(parcel.name, name)
            if s > score:
                best, score = name, s
        if best is None or not is_possible(score):
            continue
        parcel.observed_units = totals[best]["units"]
        matched += 1
        wb_buildings = totals[best]["buildings"]
        if parcel.marker_count and parcel.marker_count != wb_buildings:
            disagreements.append({
                "parcel": parcel.name, "workbook_estate": best,
                "match_score": round(score, 2),
                "markers": parcel.marker_count, "workbook_buildings": wb_buildings,
                "footprints_inside": parcel.building_count,
            })

    result = {"parcels": len(parcels), "matched": matched,
              "disagreements": disagreements[:25],
              "disagreement_count": len(disagreements),
              "note": ("Building counts differ between the perimeter survey and "
                       "the workbook for these parcels. Both are retained; "
                       "neither is assumed correct.")
              if disagreements else "Counts agree where both are present."}
    audit_service.record(
        db, actor=user, entity_type="parcel", entity_id=None,
        action="attach_units", project_id=project.id,
        changes={"result": {"before": None, "after":
                            {k: v for k, v in result.items()
                             if k != "disagreements"}}})
    db.commit()
    return result


def summary(db: Session, project_id: uuid.UUID) -> dict:
    parcels = list(db.scalars(select(Parcel).where(Parcel.project_id == project_id)))
    if not parcels:
        return {"available": False, "reason": "No estate perimeters imported yet."}
    with_units = [p for p in parcels if p.observed_units or p.declared_units]
    inside = sum(p.building_count for p in parcels)
    total_buildings = db.scalar(select(func.count()).select_from(Building)
                                .where(Building.project_id == project_id)) or 0
    return {
        "available": True,
        "parcels": len(parcels),
        "total_area_sqm": round(sum(float(p.area_sqm) for p in parcels), 1),
        "buildings_inside_parcels": inside,
        "buildings_total": total_buildings,
        "coverage_pct": (round(inside / total_buildings * 100, 1)
                         if total_buildings else 0.0),
        "parcels_with_units": len(with_units),
        "units_total": sum(p.observed_units or p.declared_units or 0
                           for p in parcels),
        "parcels_with_markers": sum(1 for p in parcels if p.marker_count),
    }


def import_name_points(db: Session, user: User, project: Project,
                       filename: str, data: bytes) -> dict:
    """Name parcels from labelled points dropped inside them.

    A point carrying the estate name inside a perimeter is an unambiguous
    naming, so it is applied directly rather than proposed.
    """
    try:
        markers = parse_markers(filename, data)
    except ParcelParseError as exc:
        raise ParcelError(str(exc)) from exc

    parcels = [(p, to_shape(p.geom)) for p in db.scalars(
        select(Parcel).where(Parcel.project_id == project.id))]
    if not parcels:
        raise ParcelError("Import estate perimeters before the name points.")

    named, skipped, orphaned, conflicts = 0, 0, 0, []
    for marker in markers:
        label = marker.label.strip()
        if not label:
            continue
        hit = next((p for p, g in parcels if g.contains(marker.geometry)), None)
        if hit is None:
            orphaned += 1
            continue
        # A real name already in place is not overwritten by a second point.
        if not looks_unnamed(hit.name, hit.survey_code):
            if similarity(hit.name, label) < 0.6:
                conflicts.append({"parcel_code": hit.parcel_code,
                                  "existing": hit.name, "point": label})
            skipped += 1
            continue
        hit.name = label
        hit.verification_state = "field_observed"
        named += 1

    result = {"points": len(markers), "parcels_named": named,
              "already_named": skipped, "orphaned_points": orphaned,
              "conflicts": conflicts[:20], "conflict_count": len(conflicts)}
    audit_service.record(
        db, actor=user, entity_type="parcel", entity_id=None,
        action="name_from_points", project_id=project.id,
        changes={"file": {"before": None, "after": filename},
                 "result": {"before": None,
                            "after": {k: v for k, v in result.items()
                                      if k != "conflicts"}}})
    db.commit()
    return result


def rename_parcel(db: Session, user: User, project: Project,
                  parcel_id: uuid.UUID, name: str) -> dict:
    parcel = db.scalar(select(Parcel).where(Parcel.id == parcel_id,
                                            Parcel.project_id == project.id))
    if parcel is None:
        raise ParcelError("Parcel not found.")
    name = name.strip()
    if len(name) < 2:
        raise ParcelError("An estate name must be at least two characters.")

    before = {"name": parcel.name, "verification_state": parcel.verification_state}
    parcel.name = name
    parcel.verification_state = "field_observed"
    audit_service.record(
        db, actor=user, entity_type="parcel", entity_id=parcel.id,
        action="rename", project_id=project.id,
        changes=audit_service.diff(before, {
            "name": parcel.name,
            "verification_state": parcel.verification_state}))
    db.commit()
    db.refresh(parcel)
    return {"id": str(parcel.id), "parcel_code": parcel.parcel_code,
            "name": parcel.name}


def listing(db: Session, project_id: uuid.UUID) -> dict:
    """Every parcel, flagged by whether it still needs a real name."""
    rows = []
    for p in db.scalars(select(Parcel).where(Parcel.project_id == project_id)
                        .order_by(Parcel.area_sqm.desc())):
        rows.append({
            "id": str(p.id), "parcel_code": p.parcel_code, "name": p.name,
            "raw_name": p.raw_name, "survey_code": p.survey_code,
            "area_sqm": float(p.area_sqm),
            "buildings": p.building_count, "markers": p.marker_count,
            "units": p.observed_units or p.declared_units,
            "needs_name": looks_unnamed(p.name, p.survey_code),
            "verification_state": p.verification_state,
        })
    return {
        "total": len(rows),
        "needing_name": sum(1 for r in rows if r["needs_name"]),
        "parcels": rows,
    }
