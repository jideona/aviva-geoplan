from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.services import project_service, readiness_service
from app.services.project_service import ProjectError

router = APIRouter(prefix="/projects/{project_id}", tags=["readiness"])


@router.get("/readiness")
def readiness(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    """The project's workflow state: what is done, what is next, what is
    blocked and why."""
    try:
        project = project_service.get_project(db, user, project_id)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc
    return readiness_service.readiness(db, project)
