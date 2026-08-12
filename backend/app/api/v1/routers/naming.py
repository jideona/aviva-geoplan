from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbSession, require
from app.core.permissions import Permission
from app.domain.naming import RULES, NameSource
from app.services import naming_service, project_service
from app.services.naming_service import NamingError
from app.services.project_service import ProjectError

router = APIRouter(prefix="/projects/{project_id}/naming", tags=["street naming"])


class NameRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    source: str
    note: str | None = None
    evidence_key: str | None = None


class BulkEntry(BaseModel):
    street_id: UUID
    name: str = Field(min_length=2, max_length=200)
    source: str
    note: str | None = None


def _project(db, user, project_id: UUID):
    try:
        return project_service.get_project(db, user, project_id)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc


@router.get("/sources")
def sources() -> dict:
    """The permitted name sources and what each implies."""
    return {
        "sources": [
            {
                "value": s.value,
                "licence_class": RULES[s].licence_class.value,
                "verification_state": RULES[s].verification.value,
                "commercial_ready": RULES[s].commercial_ready,
                "note": RULES[s].note,
            }
            for s in NameSource
        ]
    }


@router.post("/streets/{street_id}")
def name_street(project_id: UUID, street_id: UUID, payload: NameRequest,
                db: DbSession,
                user=Depends(require(Permission.GIS_EDIT))) -> dict:
    project = _project(db, user, project_id)
    try:
        s = naming_service.name_street(
            db, user, project, street_id, payload.name, payload.source,
            payload.note, payload.evidence_key)
    except NamingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc
    return {"id": str(s.id), "street_code": s.street_code, "name": s.name,
            "name_source": s.name_source, "licence_class": s.licence_class,
            "verification_state": s.verification_state,
            "needs_field_name": s.needs_field_name}


@router.post("/bulk")
def bulk(project_id: UUID, entries: list[BulkEntry], db: DbSession,
         user=Depends(require(Permission.GIS_EDIT))) -> dict:
    project = _project(db, user, project_id)
    return naming_service.bulk_name(
        db, user, project, [e.model_dump() for e in entries])


@router.post("/consolidate")
def consolidate(project_id: UUID, db: DbSession,
                user=Depends(require(Permission.GIS_EDIT))) -> dict:
    """Fold segments that already share a name into one street each.

    OSM splits ways at junctions, so a single road imports as many rows. Naming
    now merges automatically; this cleans up names entered before it did.
    """
    project = _project(db, user, project_id)
    return naming_service.consolidate(db, user, project)


@router.get("/clearance")
def clearance(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    """Could this register be delivered commercially today, and if not, what
    is the bounded remedy."""
    _project(db, user, project_id)
    return naming_service.clearance(db, project_id)
