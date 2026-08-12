from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, status

from app.api.deps import DbSession, require
from app.core.permissions import Permission
from app.services import facility_edit_service, project_service
from app.services.facility_edit_service import FacilityEditError
from app.services.project_service import ProjectError

router = APIRouter(prefix="/projects/{project_id}/design", tags=["facility edit"])


def _project(db, user, project_id):
    try:
        return project_service.get_project(db, user, project_id)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc


@router.patch("/fat/{zone_id}/position")
def move_fat(project_id: UUID, zone_id: UUID, db: DbSession,
             lon: float = Body(..., embed=True), lat: float = Body(..., embed=True),
             user=Depends(require(Permission.GIS_EDIT))) -> dict:
    project = _project(db, user, project_id)
    try:
        return facility_edit_service.move_fat(db, user, project, zone_id, lon, lat)
    except FacilityEditError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.patch("/fdh/{fdh_id}/position")
def move_fdh(project_id: UUID, fdh_id: UUID, db: DbSession,
             lon: float = Body(..., embed=True), lat: float = Body(..., embed=True),
             user=Depends(require(Permission.GIS_EDIT))) -> dict:
    project = _project(db, user, project_id)
    try:
        return facility_edit_service.move_fdh(db, user, project, fdh_id, lon, lat)
    except FacilityEditError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc
