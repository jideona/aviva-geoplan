"""Remove streets that aren't streets (bad imports / artifacts).

All foreign keys to street.id are ON DELETE SET NULL, so deleting a street
cleanly clears any building assignment, design road reference, parcel or survey
link. Streets are re-importable, so this is a hard delete rather than a
reversible exclusion.
"""
import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.street import Street
from app.db.models.project import Project
from app.db.models.user import User
from app.services import audit_service


class StreetEditError(ValueError):
    """Message is safe to show the user."""


def delete_by_codes(db: Session, user: User, project: Project,
                    codes: list[str]) -> dict:
    # Accept messy paste: split on commas/whitespace, strip, upper-case.
    wanted = {c.strip().upper() for c in
              re.split(r"[,\s]+", " ".join(codes or [])) if c.strip()}
    if not wanted:
        raise StreetEditError("No street codes provided.")
    rows = list(db.scalars(select(Street).where(
        Street.project_id == project.id,
        func.upper(Street.street_code).in_(wanted))))
    found = {r.street_code.upper() for r in rows}
    for r in rows:
        db.delete(r)
    if rows:
        audit_service.record(db, actor=user, entity_type="project",
                             entity_id=project.id, action="delete_streets",
                             project_id=project.id,
                             changes={"codes": {"before": None,
                                                "after": sorted(found)}})
        db.commit()
    return {"deleted": len(rows), "deleted_codes": sorted(found),
            "not_found": sorted(wanted - found)}


def delete_one(db: Session, user: User, project: Project,
               street_id: uuid.UUID) -> dict:
    s = db.scalar(select(Street).where(Street.id == street_id,
                                       Street.project_id == project.id))
    if s is None:
        raise StreetEditError("Street not found.")
    code = s.street_code
    db.delete(s)
    audit_service.record(db, actor=user, entity_type="street", entity_id=street_id,
                         action="delete_street", project_id=project.id,
                         changes={"code": {"before": code, "after": None}})
    db.commit()
    return {"deleted": 1, "code": code}
