"""Trace drop corridors — footpaths, pathways and fence lines a drop follows.

A corridor is a line, captured exactly like a hand-drawn building: its capture
source fixes its licence class, so a fence traced over display-only Esri imagery
stays pilot-only until re-sourced. Corridors feed the drop-routing graph and
nothing else (see app.services.design_service.drops_geojson).
"""
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import LineString, shape
from shapely.ops import transform
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.corridor import CORRIDOR_TYPES, Corridor
from app.db.models.project import Project
from app.db.models.user import User
from app.domain.building_edit import CaptureSource, rules_for
from app.domain.crs import STORAGE_EPSG, _transformer
from app.services import audit_service

MIN_LENGTH_M = 2.0
MAX_LENGTH_M = 5_000.0


class CorridorError(ValueError):
    """Message is safe to show the user."""


def create_corridor(db: Session, user: User, project: Project,
                    geometry: dict, corridor_type: str, source: str) -> dict:
    try:
        geom = shape(geometry)
    except (TypeError, ValueError) as exc:
        raise CorridorError(f"Geometry could not be read: {exc}") from exc
    if not isinstance(geom, LineString) or geom.is_empty:
        raise CorridorError("A corridor must be a line with at least two points.")
    if corridor_type not in CORRIDOR_TYPES:
        raise CorridorError(
            f"Unknown corridor type {corridor_type!r}. Valid: "
            f"{', '.join(CORRIDOR_TYPES)}")
    try:
        rules = rules_for(source)
    except (KeyError, ValueError) as exc:
        raise CorridorError(
            f"Unknown capture source {source!r}. Valid: "
            f"{', '.join(s.value for s in CaptureSource)}") from exc

    to_metric = _transformer(STORAGE_EPSG, project.metric_crs_epsg).transform
    length = transform(to_metric, geom).length
    if length < MIN_LENGTH_M:
        raise CorridorError(f"Corridor {length:.0f} m is below the "
                            f"{MIN_LENGTH_M:.0f} m minimum — likely a mis-click.")
    if length > MAX_LENGTH_M:
        raise CorridorError(f"Corridor {length:,.0f} m is implausibly long.")

    row = Corridor(
        project_id=project.id, corridor_type=corridor_type,
        geom=from_shape(geom, srid=4326), length_m=round(length, 2),
        capture_source=source, licence_class=rules["licence_class"],
        verification_state=rules["verification_state"],
        commercial_ready=rules["commercial_ready"], created_by=user.email)
    db.add(row)
    db.flush()
    audit_service.record(
        db, actor=user, entity_type="corridor", entity_id=row.id,
        action="create_corridor", project_id=project.id,
        changes={"type": {"before": None, "after": corridor_type},
                 "length_m": {"before": None, "after": round(length, 2)}})
    db.commit()
    return {"id": str(row.id), "corridor_type": corridor_type,
            "length_m": round(length, 1), "licence_class": rules["licence_class"],
            "commercial_ready": rules["commercial_ready"]}


def delete_corridor(db: Session, user: User, project: Project,
                    corridor_id) -> None:
    row = db.scalar(select(Corridor).where(
        Corridor.id == corridor_id, Corridor.project_id == project.id))
    if row is None:
        raise CorridorError("Corridor not found.")
    db.delete(row)
    audit_service.record(
        db, actor=user, entity_type="corridor", entity_id=corridor_id,
        action="delete_corridor", project_id=project.id, changes={})
    db.commit()


def corridors_geojson(db: Session, project: Project) -> dict:
    from shapely.geometry import mapping
    features = []
    for c in db.scalars(select(Corridor).where(
            Corridor.project_id == project.id)):
        features.append({
            "type": "Feature", "geometry": mapping(to_shape(c.geom)),
            "properties": {"id": str(c.id), "corridor_type": c.corridor_type,
                           "length_m": float(c.length_m),
                           "licence_class": c.licence_class,
                           "commercial_ready": c.commercial_ready}})
    return {"type": "FeatureCollection", "features": features}
