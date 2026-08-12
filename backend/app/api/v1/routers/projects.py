from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import CurrentUser, DbSession, require
from app.core.permissions import Permission
from app.db.models.project import Project
from app.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate
from app.services import project_service
from app.services.project_service import ProjectError

router = APIRouter(prefix="/projects", tags=["projects"])


def _out(db, project: Project) -> ProjectOut:
    boundary = project_service.current_boundary(db, project.id)
    dto = ProjectOut.model_validate(project)
    dto.has_boundary = boundary is not None
    dto.boundary_area_sqkm = float(boundary.area_sqkm) if boundary else None
    return dto


@router.get("", response_model=list[ProjectOut])
def list_projects(db: DbSession, user: CurrentUser) -> list[ProjectOut]:
    return [_out(db, p) for p in project_service.list_projects(db, user)]


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    db: DbSession,
    user=Depends(require(Permission.PROJECT_CREATE)),
) -> ProjectOut:
    try:
        return _out(db, project_service.create_project(db, user, payload))
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: UUID, db: DbSession, user: CurrentUser) -> ProjectOut:
    try:
        return _out(db, project_service.get_project(db, user, project_id))
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    db: DbSession,
    user=Depends(require(Permission.PROJECT_EDIT)),
) -> ProjectOut:
    try:
        return _out(db, project_service.update_project(db, user, project_id, payload))
    except ProjectError as exc:
        code = (status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower()
                else status.HTTP_400_BAD_REQUEST)
        raise HTTPException(status_code=code, detail=str(exc)) from exc
