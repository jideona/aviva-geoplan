from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import CurrentUser, DbSession, require
from app.core.permissions import Permission
from app.schemas.boundary import BoundaryOut
from app.services import boundary_service, project_service
from app.services.boundary_service import BoundaryError
from app.services.project_service import ProjectError

router = APIRouter(prefix="/projects/{project_id}/boundary", tags=["boundaries"])


def _out(boundary) -> BoundaryOut:
    return BoundaryOut(
        id=boundary.id,
        project_id=boundary.project_id,
        area_sqkm=float(boundary.area_sqkm),
        source_filename=boundary.source_filename,
        verification_state=boundary.verification_state,
        created_at=boundary.created_at,
        geometry=boundary_service.as_geojson(boundary),
    )


@router.post("", response_model=BoundaryOut, status_code=status.HTTP_201_CREATED)
async def upload_boundary(
    project_id: UUID,
    db: DbSession,
    file: UploadFile = File(...),
    user=Depends(require(Permission.GIS_IMPORT)),
) -> BoundaryOut:
    try:
        project = project_service.get_project(db, user, project_id)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc

    data = await file.read()
    try:
        boundary = boundary_service.set_boundary(
            db, user, project, file.filename or "boundary", data)
    except BoundaryError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc
    return _out(boundary)


@router.get("", response_model=BoundaryOut)
def get_boundary(project_id: UUID, db: DbSession, user: CurrentUser) -> BoundaryOut:
    try:
        project_service.get_project(db, user, project_id)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc

    boundary = boundary_service.get_current(db, project_id)
    if boundary is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="This project has no boundary yet.")
    return _out(boundary)
