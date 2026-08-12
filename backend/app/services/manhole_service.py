"""Surveyed manhole / chamber capture from the field.

Field capture is the highest-trust source (field_surveyed → owned,
field_observed), so a manhole created here is authoritative. Creates carry a
client-generated id so an offline capture replayed on reconnect is idempotent.
"""
import uuid
from datetime import datetime, timezone

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point, mapping
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.manhole import CONDITIONS, MANHOLE_TYPES, Manhole
from app.db.models.project import Project
from app.db.models.user import User
from app.services import audit_service


class ManholeError(ValueError):
    """Message is safe to show the user."""


def create(db: Session, user: User, project: Project, *, lon: float, lat: float,
           manhole_type: str = "manhole", condition: str = "unknown",
           code: str | None = None, condition_notes: str | None = None,
           gps_accuracy_m: float | None = None, client_id: str | None = None,
           survey_session_id: uuid.UUID | None = None) -> dict:
    if manhole_type not in MANHOLE_TYPES:
        raise ManholeError(f"type must be one of {', '.join(MANHOLE_TYPES)}.")
    if condition not in CONDITIONS:
        raise ManholeError(f"condition must be one of {', '.join(CONDITIONS)}.")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ManholeError("Coordinates are out of range.")

    if client_id:                       # idempotent replay of an offline capture
        existing = db.scalar(select(Manhole).where(
            Manhole.project_id == project.id, Manhole.client_id == client_id))
        if existing is not None:
            return _out(existing)

    row = Manhole(
        project_id=project.id, client_id=client_id, code=code,
        manhole_type=manhole_type, geom=from_shape(Point(lon, lat), srid=4326),
        gps_accuracy_m=gps_accuracy_m, condition=condition,
        condition_notes=condition_notes,
        assessed_at=datetime.now(timezone.utc) if condition != "unknown" else None,
        surveyed_by=user.email, survey_session_id=survey_session_id,
        licence_class="owned", verification_state="field_observed")
    db.add(row)
    db.flush()
    audit_service.record(db, actor=user, entity_type="manhole", entity_id=row.id,
                         action="capture_manhole", project_id=project.id,
                         changes={"condition": {"before": None, "after": condition}})
    db.commit()
    db.refresh(row)
    return _out(row)


def update_condition(db: Session, user: User, project: Project,
                     manhole_id: uuid.UUID, *, condition: str | None = None,
                     condition_notes: str | None = None,
                     code: str | None = None,
                     lon: float | None = None, lat: float | None = None) -> dict:
    row = db.scalar(select(Manhole).where(
        Manhole.id == manhole_id, Manhole.project_id == project.id))
    if row is None:
        raise ManholeError("Manhole not found.")
    if condition is not None:
        if condition not in CONDITIONS:
            raise ManholeError(f"condition must be one of {', '.join(CONDITIONS)}.")
        row.condition = condition
        row.assessed_at = datetime.now(timezone.utc)
    if condition_notes is not None:
        row.condition_notes = condition_notes
    if code is not None:
        row.code = code
    # Repositioning — a surveyor dragging the pin to the actual spot after a
    # rough initial drop, or nudging it once a satellite/street view makes
    # the real location obvious. Both lon and lat must be given together
    # since a lone coordinate can't build a valid point.
    if lon is not None and lat is not None:
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ManholeError("Coordinates are out of range.")
        row.geom = from_shape(Point(lon, lat), srid=4326)
    audit_service.record(db, actor=user, entity_type="manhole", entity_id=row.id,
                         action="assess_manhole", project_id=project.id,
                         changes={"condition": {"before": None, "after": row.condition}})
    db.commit()
    return _out(row)


def set_excluded(db: Session, user: User, project: Project,
                 manhole_id: uuid.UUID) -> dict:
    """Soft-delete — field captures stay in the audit trail rather than being
    hard-deleted, mirroring building_edit_service.set_excluded. geojson()
    below already filters excluded=False, so this makes the manhole disappear
    from the map/sync feed immediately without losing the record."""
    row = db.scalar(select(Manhole).where(
        Manhole.id == manhole_id, Manhole.project_id == project.id))
    if row is None:
        raise ManholeError("Manhole not found.")
    row.excluded = True
    audit_service.record(db, actor=user, entity_type="manhole", entity_id=row.id,
                         action="exclude", project_id=project.id,
                         changes={"excluded": {"before": False, "after": True}})
    db.commit()
    return {"id": str(row.id), "excluded": True}


def geojson(db: Session, project: Project, since: datetime | None = None) -> dict:
    q = select(Manhole).where(Manhole.project_id == project.id,
                              Manhole.excluded.is_(False))
    if since is not None:
        q = q.where(Manhole.updated_at > since)
    features = [{
        "type": "Feature", "geometry": mapping(to_shape(m.geom)),
        "properties": {"id": str(m.id), "code": m.code, "type": m.manhole_type,
                       "condition": m.condition, "notes": m.condition_notes,
                       "surveyed_by": m.surveyed_by,
                       "assessed_at": m.assessed_at.isoformat() if m.assessed_at else None,
                       "updated_at": m.updated_at.isoformat()}}
        for m in db.scalars(q)]
    return {"type": "FeatureCollection", "features": features}


def _out(m: Manhole) -> dict:
    p = to_shape(m.geom)
    return {"id": str(m.id), "client_id": m.client_id, "code": m.code,
            "manhole_type": m.manhole_type, "lon": p.x, "lat": p.y,
            "condition": m.condition, "condition_notes": m.condition_notes,
            "verification_state": m.verification_state,
            "updated_at": m.updated_at.isoformat()}
