from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, DbSession, require
from app.core.permissions import Permission
from app.db.models.corridor import CORRIDOR_TYPES
from app.services import corridor_service, project_service
from app.services.corridor_service import CorridorError
from app.services.project_service import ProjectError

router = APIRouter(prefix="/projects/{project_id}/corridors", tags=["corridors"])


class CreateCorridor(BaseModel):
    geometry: dict
    corridor_type: str = "footpath"
    source: str = "traced_reference"


def _project(db, user, project_id):
    try:
        return project_service.get_project(db, user, project_id)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc


@router.get("/types")
def corridor_types() -> dict:
    return {"types": list(CORRIDOR_TYPES)}


@router.get(".geojson")
def corridors_geojson(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    project = _project(db, user, project_id)
    return corridor_service.corridors_geojson(db, project)


@router.post("")
def create_corridor(project_id: UUID, db: DbSession,
                    payload: CreateCorridor = Body(...),
                    user=Depends(require(Permission.GIS_EDIT))) -> dict:
    project = _project(db, user, project_id)
    try:
        return corridor_service.create_corridor(
            db, user, project, payload.geometry, payload.corridor_type,
            payload.source)
    except CorridorError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.delete("/{corridor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_corridor(project_id: UUID, corridor_id: UUID, db: DbSession,
                    user=Depends(require(Permission.GIS_EDIT))) -> None:
    project = _project(db, user, project_id)
    try:
        corridor_service.delete_corridor(db, user, project, corridor_id)
    except CorridorError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc
