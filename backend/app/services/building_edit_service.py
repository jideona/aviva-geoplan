"""Create, move and retire buildings by hand (SRD FR-GIS-005, FR-GIS-008)."""
import math
import uuid

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Polygon, mapping, shape
from shapely.ops import transform
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.building import BUILDING_CONDITIONS, Building
from app.db.models.project import Project
from app.db.models.building_manhole_link import BuildingManholeLink
from app.db.models.manhole import Manhole
from app.db.models.provenance import DataSource, ProvenanceRecord
from app.db.models.user import User
from app.domain.building_edit import CaptureSource, rules_for
from app.domain.crs import STORAGE_EPSG, _transformer
from app.services import audit_service, boundary_service

MIN_SQM = 3.0
MAX_SQM = 100_000.0

_SOURCE_NAME = {
    "field_surveyed": "Aviva field survey (drawn)",
    "traced_owned": "Aviva drone trace",
    "traced_reference": "Reference imagery trace (Esri)",
    "manual": "Manual entry",
}


class BuildingEditError(ValueError):
    """Message is safe to show the user."""


def create_building(db: Session, user: User, project: Project,
                    geometry: dict, source: str) -> dict:
    try:
        geom = shape(geometry)
    except (TypeError, ValueError) as exc:
        raise BuildingEditError(f"Geometry could not be read: {exc}") from exc
    if not isinstance(geom, Polygon):
        raise BuildingEditError("A building must be a polygon.")
    if not geom.is_valid:
        geom = geom.buffer(0)
    if geom.is_empty or not isinstance(geom, Polygon):
        raise BuildingEditError("The drawn shape is not a valid polygon.")

    try:
        rules = rules_for(source)
    except (KeyError, ValueError) as exc:
        raise BuildingEditError(
            f"Unknown capture source {source!r}. Valid: "
            f"{', '.join(s.value for s in CaptureSource)}") from exc

    boundary = boundary_service.get_current(db, project.id)
    if boundary is not None and not to_shape(boundary.geom).contains(geom.centroid):
        raise BuildingEditError("The drawn building is outside the project boundary.")

    to_metric = _transformer(STORAGE_EPSG, project.metric_crs_epsg).transform
    metric = transform(to_metric, geom)
    area = metric.area
    if area < MIN_SQM:
        raise BuildingEditError(f"Footprint {area:.0f} m² is below the "
                                f"{MIN_SQM:.0f} m² minimum — likely a mis-click.")
    if area > MAX_SQM:
        raise BuildingEditError(f"Footprint {area:,.0f} m² is implausibly large.")

    name = _SOURCE_NAME.get(source, "Manual entry")
    src = db.scalar(select(DataSource).where(DataSource.name == name))
    if src is None:
        src = DataSource(name=name, source_type="manual_entry",
                         licence_class=rules["licence_class"],
                         admitted_role="Hand-captured building.")
        db.add(src)
        db.flush()

    b = Building(
        project_id=project.id,
        geom=from_shape(geom, srid=4326),
        centroid=from_shape(geom.centroid, srid=4326),
        footprint_area_sqm=round(area, 2),
        perimeter_m=round(metric.length, 2),
        building_type="unclassified", use_type="unknown",
        data_source_id=src.id, source_dataset=name,
        licence_class=rules["licence_class"],
        verification_state=rules["verification_state"],
        last_edited_by=user.email,
        detection_confidence=1.0)
    db.add(b)
    db.flush()
    db.add(ProvenanceRecord(entity_type="building", entity_id=b.id,
                            data_source_id=src.id, imported_at=func.now(),
                            notes=f"Hand-drawn: {source}"))
    audit_service.record(db, actor=user, entity_type="building", entity_id=b.id,
                         action="create_manual", project_id=project.id,
                         changes={"area_sqm": {"before": None, "after": round(area, 2)},
                                  "source": {"before": None, "after": source}})
    db.commit()
    db.refresh(b)
    return {"id": str(b.id), "area_sqm": float(b.footprint_area_sqm),
            "licence_class": b.licence_class,
            "verification_state": b.verification_state,
            "commercial_ready": rules["commercial_ready"]}


def move_building(db: Session, user: User, project: Project,
                  building_id: uuid.UUID, geometry: dict) -> dict:
    b = db.scalar(select(Building).where(Building.id == building_id,
                                         Building.project_id == project.id))
    if b is None:
        raise BuildingEditError("Building not found.")
    try:
        geom = shape(geometry)
    except (TypeError, ValueError) as exc:
        raise BuildingEditError(f"Geometry could not be read: {exc}") from exc
    if not geom.is_valid:
        geom = geom.buffer(0)
    to_metric = _transformer(STORAGE_EPSG, project.metric_crs_epsg).transform
    metric = transform(to_metric, geom)
    before = {"area_sqm": float(b.footprint_area_sqm)}
    b.geom = from_shape(geom, srid=4326)
    b.centroid = from_shape(geom.centroid, srid=4326)
    b.footprint_area_sqm = round(metric.area, 2)
    b.perimeter_m = round(metric.length, 2)
    b.last_edited_by = user.email
    audit_service.record(db, actor=user, entity_type="building", entity_id=b.id,
                         action="edit_geometry", project_id=project.id,
                         changes=audit_service.diff(before,
                             {"area_sqm": float(b.footprint_area_sqm)}))
    db.commit()
    return {"id": str(b.id), "area_sqm": float(b.footprint_area_sqm)}


def delete_building(db: Session, user: User, project: Project,
                    building_id: uuid.UUID) -> dict:
    b = db.scalar(select(Building).where(Building.id == building_id,
                                         Building.project_id == project.id))
    if b is None:
        raise BuildingEditError("Building not found.")
    audit_service.record(db, actor=user, entity_type="building", entity_id=b.id,
                         action="delete", project_id=project.id,
                         changes={"deleted": {"before": False, "after": True}})
    db.delete(b)
    db.commit()
    return {"deleted": str(building_id)}


def set_excluded(db: Session, user: User, project: Project,
                 building_id: uuid.UUID, excluded: bool,
                 reason: str | None = None) -> dict:
    b = db.scalar(select(Building).where(Building.id == building_id,
                                         Building.project_id == project.id))
    if b is None:
        raise BuildingEditError("Building not found.")
    before = {"excluded": b.excluded}
    b.excluded = excluded
    b.excluded_reason = reason if excluded else None
    b.last_edited_by = user.email
    if excluded:
        b.serving_zone_id = None      # drop it out of any current design
    audit_service.record(db, actor=user, entity_type="building", entity_id=b.id,
                         action="exclude" if excluded else "restore",
                         project_id=project.id,
                         changes=audit_service.diff(before, {"excluded": excluded}))
    db.commit()
    return {"id": str(b.id), "excluded": b.excluded}


_TYPES = ("unclassified", "residential", "commercial", "mixed_use",
          "industrial", "institutional", "religious", "under_construction",
          # Row/terrace typology (SRD: surveyors capturing a block that is
          # actually N terrace units, see units_surveyed below) — was missing
          # here even though the Building model's own BUILDING_TYPES has
          # long included "terrace"; field updates using it were silently
          # rejected by this separate validation list.
          "terrace", "other")
_USES = ("unknown", "single_dwelling", "apartments", "shop", "office",
         "warehouse", "school", "clinic", "worship", "mixed", "other")


def nearest(db: Session, project: Project, lat: float, lon: float,
            limit: int = 15) -> list[dict]:
    """Buildings closest to a GPS point — so a surveyor standing next to one can
    pick it from a short list rather than hunt on a map."""
    from sqlalchemy import func
    pt = func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)
    dist = func.ST_DistanceSphere(Building.centroid, pt)
    rows = db.execute(
        select(Building.id, Building.building_code, Building.building_type,
               Building.use_type, Building.address, Building.units_surveyed,
               Building.drop_deployment, Building.notes, Building.condition,
               dist.label("dist"))
        .where(Building.project_id == project.id, Building.excluded.is_(False))
        .order_by(dist).limit(limit)).all()
    return [{"id": str(r.id), "code": r.building_code,
             "building_type": r.building_type, "use_type": r.use_type,
             "address": r.address, "units_surveyed": r.units_surveyed,
             "drop_deployment": r.drop_deployment, "notes": r.notes,
             "condition": r.condition,
             "distance_m": round(r.dist, 1)} for r in rows]


def update_attributes(db: Session, user: User, project: Project,
                      building_id: uuid.UUID, attrs: dict) -> dict:
    """Field update of a building's classification/address/units. Marks the
    record field-observed (highest trust) with an audit trail."""
    b = db.scalar(select(Building).where(Building.id == building_id,
                                         Building.project_id == project.id))
    if b is None:
        raise BuildingEditError("Building not found.")
    if "building_type" in attrs and attrs["building_type"] not in _TYPES:
        raise BuildingEditError(f"building_type must be one of {', '.join(_TYPES)}.")
    if "use_type" in attrs and attrs["use_type"] not in _USES:
        raise BuildingEditError(f"use_type must be one of {', '.join(_USES)}.")
    if "units_surveyed" in attrs and attrs["units_surveyed"] is not None \
            and int(attrs["units_surveyed"]) < 0:
        raise BuildingEditError("units_surveyed cannot be negative.")
    if "drop_deployment" in attrs and attrs["drop_deployment"] not in (
            "aerial", "underground", None):
        raise BuildingEditError(
            "drop_deployment must be 'aerial', 'underground' or null.")
    if "condition" in attrs and attrs["condition"] is not None \
            and attrs["condition"] not in BUILDING_CONDITIONS:
        raise BuildingEditError(
            f"condition must be one of {', '.join(BUILDING_CONDITIONS)}, or null.")

    before = {}
    for field in ("building_type", "use_type", "address", "units_surveyed",
                  "drop_deployment", "notes", "condition"):
        if field in attrs:
            before[field] = getattr(b, field)
            setattr(b, field, attrs[field])
    b.verification_state = "field_observed"        # field capture is authoritative
    b.last_edited_by = user.email
    audit_service.record(db, actor=user, entity_type="building", entity_id=b.id,
                         action="field_update", project_id=project.id,
                         changes=audit_service.diff(
                             before, {k: attrs[k] for k in before}))
    db.commit()
    return {"id": str(b.id), "building_type": b.building_type,
            "use_type": b.use_type, "address": b.address,
            "units_surveyed": b.units_surveyed,
            "drop_deployment": b.drop_deployment, "notes": b.notes,
            "condition": b.condition,
            "verification_state": b.verification_state}


def link_manholes(db: Session, user: User, project: Project,
                  building_id: uuid.UUID, manhole_ids: list[uuid.UUID]) -> dict:
    """Replace this building's "Associated Assets" — the manholes it's linked
    to. Full-replace semantics (not add/remove) to match the field app's
    fixed picker slots: sending [] clears all links. Silently drops any id
    that isn't actually a manhole in this project, rather than failing the
    whole save over one bad reference.
    """
    b = db.scalar(select(Building).where(Building.id == building_id,
                                         Building.project_id == project.id))
    if b is None:
        raise BuildingEditError("Building not found.")
    valid_ids = set(db.scalars(select(Manhole.id).where(
        Manhole.project_id == project.id, Manhole.id.in_(manhole_ids))))
    for link in list(db.scalars(select(BuildingManholeLink).where(
            BuildingManholeLink.building_id == building_id))):
        db.delete(link)
    for mid in dict.fromkeys(manhole_ids):
        if mid in valid_ids:
            db.add(BuildingManholeLink(building_id=building_id, manhole_id=mid,
                                       created_by=user.email))
    db.commit()
    return linked_manholes(db, project, building_id)


def linked_manholes(db: Session, project: Project, building_id: uuid.UUID) -> dict:
    rows = db.execute(
        select(Manhole.id, Manhole.code, Manhole.manhole_type)
        .join(BuildingManholeLink, BuildingManholeLink.manhole_id == Manhole.id)
        .where(BuildingManholeLink.building_id == building_id,
               Manhole.project_id == project.id)).all()
    return {"linked_manholes": [
        {"id": str(mid), "code": code, "manhole_type": mtype}
        for mid, code, mtype in rows]}


def cleanup_noise(db: Session, user: User, project: Project,
                  min_area_sqm: float = 10.0, max_circularity: float = 0.88,
                  dry_run: bool = True) -> dict:
    """Find (and optionally exclude) footprints that are almost certainly not
    buildings: tiny slivers below a plausible minimum, and near-circular blobs
    (tree canopies, tanks) — a rooftop is rectangular, so its circularity
    (4*pi*area/perimeter^2) is well below 1. Uses the stored metric area and
    perimeter, so it is cheap. Exclusion is reversible (Restore), never a hard
    delete, so a mistaken sweep can be undone.
    """
    rows = list(db.scalars(select(Building).where(
        Building.project_id == project.id, Building.excluded.is_(False))))
    tiny = round_ = 0
    matches = []
    for b in rows:
        area = float(b.footprint_area_sqm or 0)
        peri = float(b.perimeter_m or 0)
        circ = (4 * math.pi * area / (peri * peri)) if peri > 0 else 0.0
        is_tiny = area < min_area_sqm
        is_round = circ >= max_circularity
        if is_tiny or is_round:
            matches.append(b)
            tiny += 1 if is_tiny else 0
            round_ += 1 if (is_round and not is_tiny) else 0

    summary = {
        "candidates": len(matches), "tiny": tiny, "round": round_,
        "min_area_sqm": min_area_sqm, "max_circularity": max_circularity,
        "dry_run": dry_run,
        "note": ("Excluded footprints are hidden from the map, register and "
                 "design but kept for audit — Restore reverses it."),
    }
    if dry_run:
        summary["preview"] = {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "geometry": mapping(to_shape(b.geom)),
                          "properties": {"kind": "detect_preview",
                                         "area": float(b.footprint_area_sqm or 0)}}
                         for b in matches]}
        summary["excluded"] = 0
        return summary

    for b in matches:
        b.excluded = True
        b.excluded_reason = "auto-cleanup: non-building footprint"
        b.serving_zone_id = None
    audit_service.record(db, actor=user, entity_type="project", entity_id=project.id,
                         action="cleanup_noise", project_id=project.id,
                         changes={"excluded": {"before": None, "after": len(matches)}})
    db.commit()
    summary["excluded"] = len(matches)
    return summary


def bulk_exclude(db: Session, user: User, project: Project,
                 building_ids: list[uuid.UUID], reason: str | None) -> dict:
    n = 0
    for bid in building_ids:
        try:
            set_excluded(db, user, project, bid, True, reason)
            n += 1
        except BuildingEditError:
            continue
    return {"excluded": n}
