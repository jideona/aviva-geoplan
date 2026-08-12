from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.services import connectorised_service, project_service
from app.services.connectorised_service import ConnectorisedError
from app.services.project_service import ProjectError

router = APIRouter(prefix="/projects/{project_id}/connectorised", tags=["connectorised"])


@router.get("/envelope")
def envelope(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    """Combined equipment envelope: connectorised terminals plus splitter stock,
    phased. Does not require a design run."""
    try:
        project = project_service.get_project(db, user, project_id)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc
    return connectorised_service.combined_envelope(db, project.organisation_id)


@router.get("/fit")
def fit(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    """What the pre-connectorised underground stock can deploy against the
    current design."""
    try:
        project = project_service.get_project(db, user, project_id)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc
    try:
        return connectorised_service.fit_report(db, project)
    except ConnectorisedError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc
