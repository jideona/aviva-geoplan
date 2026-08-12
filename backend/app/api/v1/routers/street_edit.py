from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import DbSession, require
from app.core.permissions import Permission
from app.services import project_service, street_edit_service
from app.services.project_service import ProjectError
from app.services.street_edit_service import StreetEditError

router = APIRouter(prefix="/projects/{project_id}/streets", tags=["street edit"])


class DeleteCodes(BaseModel):
    codes: list[str]


def _project(db, user, project_id):
    try:
        return project_service.get_project(db, user, project_id)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc


@router.post("/delete-by-code")
def delete_by_code(project_id: UUID, payload: DeleteCodes, db: DbSession,
                   user=Depends(require(Permission.GIS_EDIT))) -> dict:
    """Delete streets by code (bad imports / non-streets). Accepts a messy
    paste — commas or whitespace between codes."""
    project = _project(db, user, project_id)
    try:
        return street_edit_service.delete_by_codes(db, user, project, payload.codes)
    except StreetEditError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.delete("/{street_id}")
def delete_street(project_id: UUID, street_id: UUID, db: DbSession,
                  user=Depends(require(Permission.GIS_EDIT))) -> dict:
    project = _project(db, user, project_id)
    try:
        return street_edit_service.delete_one(db, user, project, street_id)
    except StreetEditError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc
