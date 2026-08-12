from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession, require
from app.core.permissions import Permission
from app.schemas.deployment import DeploymentTaskCreate, DeploymentTaskUpdate
from app.services import deployment_service, project_service
from app.services.deployment_service import DeploymentError
from app.services.project_service import ProjectError

router = APIRouter(prefix="/projects/{project_id}/deployment", tags=["deployment"])


def _project(db, user, project_id: UUID):
    try:
        return project_service.get_project(db, user, project_id)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc


@router.get("/tasks")
def list_tasks(project_id: UUID, db: DbSession, user: CurrentUser,
               area: str | None = None,
               status_: str | None = Query(default=None, alias="status"),
               assignee_id: UUID | None = None) -> dict:
    """Deployment tasks for this project — replaces the "Deployment plan"
    monday.com board. Every task belongs to a real project and, optionally,
    a real GeoPlan entity, instead of a spreadsheet row with no coordinates."""
    project = _project(db, user, project_id)
    tasks = deployment_service.list_tasks(db, project, area=area, status=status_,
                                          assignee_id=assignee_id)
    return {"tasks": tasks}


@router.get("/tasks/summary")
def task_summary(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    """Counts by area/status, overdue tasks, open issues — one glance instead
    of scrolling a board."""
    project = _project(db, user, project_id)
    return deployment_service.summary(db, project)


@router.get("/assignees")
def assignees(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    """Active users in this organisation, for the assignee picker."""
    project = _project(db, user, project_id)
    return {"users": deployment_service.assignable_users(db, project)}


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
def create_task(project_id: UUID, payload: DeploymentTaskCreate, db: DbSession,
                user=Depends(require(Permission.TASK_MANAGE))) -> dict:
    project = _project(db, user, project_id)
    try:
        return deployment_service.create_task(
            db, user, project, payload.model_dump(exclude_unset=True))
    except DeploymentError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.patch("/tasks/{task_id}")
def update_task(project_id: UUID, task_id: UUID, payload: DeploymentTaskUpdate,
                db: DbSession, user: CurrentUser) -> dict:
    """Project managers / survey coordinators / construction managers can edit
    any field. Anyone else can only update status/updates/issues, and only on
    a task assigned to them — enforced in the service, since it depends on
    the row, not just the caller's role."""
    project = _project(db, user, project_id)
    try:
        return deployment_service.update_task(
            db, user, project, task_id, payload.model_dump(exclude_unset=True))
    except DeploymentError as exc:
        code = (status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower()
               else status.HTTP_403_FORBIDDEN if "only" in str(exc).lower()
               else status.HTTP_400_BAD_REQUEST)
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(project_id: UUID, task_id: UUID, db: DbSession,
                user=Depends(require(Permission.TASK_MANAGE))) -> None:
    project = _project(db, user, project_id)
    try:
        deployment_service.delete_task(db, project, task_id)
    except DeploymentError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc
