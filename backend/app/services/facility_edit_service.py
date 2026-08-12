"""Reposition FDH and FAT by hand; the move persists and locks the element."""
import uuid

from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.design import Fdh, ServingZone
from app.db.models.project import Project
from app.db.models.user import User
from app.services import audit_service


class FacilityEditError(ValueError):
    """Message is safe to show the user."""


def move_fat(db: Session, user: User, project: Project,
             zone_id: uuid.UUID, lon: float, lat: float) -> dict:
    z = db.scalar(select(ServingZone).where(ServingZone.id == zone_id,
                                            ServingZone.project_id == project.id))
    if z is None:
        raise FacilityEditError("FAT not found.")
    z.fat_point = from_shape(Point(lon, lat), srid=4326)
    z.locked = True
    audit_service.record(db, actor=user, entity_type="serving_zone",
                         entity_id=z.id, action="move", project_id=project.id,
                         changes={"moved": {"before": None, "after": [lon, lat]}})
    db.commit()
    return {"id": str(z.id), "zone_code": z.zone_code, "locked": True}


def move_fdh(db: Session, user: User, project: Project,
             fdh_id: uuid.UUID, lon: float, lat: float) -> dict:
    f = db.scalar(select(Fdh).where(Fdh.id == fdh_id,
                                    Fdh.project_id == project.id))
    if f is None:
        raise FacilityEditError("FDH not found.")
    f.point = from_shape(Point(lon, lat), srid=4326)
    audit_service.record(db, actor=user, entity_type="fdh", entity_id=f.id,
                         action="move", project_id=project.id,
                         changes={"moved": {"before": None, "after": [lon, lat]}})
    db.commit()
    return {"id": str(f.id), "fdh_code": f.fdh_code}
