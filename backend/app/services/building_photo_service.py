"""Quick field photo capture of a building — see BuildingPhoto model.

Field capture is the highest-trust source (field_surveyed → owned), so a
building photo created here is authoritative. Creates carry a client-generated
id so an offline capture replayed on reconnect is idempotent.
"""
import uuid
from datetime import datetime

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point, mapping
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.building_photo import BuildingPhoto
from app.db.models.project import Project
from app.db.models.user import User
from app.services import audit_service


class BuildingPhotoError(ValueError):
    """Message is safe to show the user."""


def create(db: Session, user: User, project: Project, *, lon: float, lat: float,
           gps_accuracy_m: float | None = None,
           client_id: str | None = None) -> dict:
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise BuildingPhotoError("Coordinates are out of range.")

    if client_id:                       # idempotent replay of an offline capture
        existing = db.scalar(select(BuildingPhoto).where(
            BuildingPhoto.project_id == project.id, BuildingPhoto.client_id == client_id))
        if existing is not None:
            return _out(existing)

    row = BuildingPhoto(
        project_id=project.id, client_id=client_id,
        geom=from_shape(Point(lon, lat), srid=4326),
        gps_accuracy_m=gps_accuracy_m, surveyed_by=user.email,
        licence_class="owned", verification_state="field_observed")
    db.add(row)
    db.flush()
    audit_service.record(db, actor=user, entity_type="building_photo", entity_id=row.id,
                         action="capture_building_photo", project_id=project.id,
                         changes={})
    db.commit()
    db.refresh(row)
    return _out(row)


def geojson(db: Session, project: Project, since: datetime | None = None) -> dict:
    q = select(BuildingPhoto).where(BuildingPhoto.project_id == project.id,
                                    BuildingPhoto.excluded.is_(False))
    if since is not None:
        q = q.where(BuildingPhoto.updated_at > since)
    features = [{
        "type": "Feature", "geometry": mapping(to_shape(bp.geom)),
        "properties": {"id": str(bp.id), "kind": "building_photo",
                       "surveyed_by": bp.surveyed_by,
                       "updated_at": bp.updated_at.isoformat()}}
        for bp in db.scalars(q)]
    return {"type": "FeatureCollection", "features": features}


def _out(bp: BuildingPhoto) -> dict:
    p = to_shape(bp.geom)
    return {"id": str(bp.id), "client_id": bp.client_id, "lon": p.x, "lat": p.y,
            "verification_state": bp.verification_state,
            "updated_at": bp.updated_at.isoformat()}
