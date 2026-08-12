from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.domain.optical import OpticalParams
from app.services import optical_service, project_service
from app.services.optical_service import OpticalError
from app.services.project_service import ProjectError

router = APIRouter(prefix="/projects/{project_id}/optical", tags=["optical"])


@router.get("/phase/{phase}")
def budget(project_id: UUID, phase: int, db: DbSession, user: CurrentUser,
           fibre_db_per_km: float = 0.35, olt_launch_dbm: float = 4.0,
           ont_sensitivity_dbm: float = -28.0,
           required_margin_db: float = 1.0) -> dict:
    """Optical loss budget for a pilot phase over its real routes."""
    if phase not in (1, 2):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Phase must be 1 or 2.")
    try:
        project = project_service.get_project(db, user, project_id)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc
    params = OpticalParams(fibre_db_per_km=fibre_db_per_km,
                           olt_launch_dbm=olt_launch_dbm,
                           ont_sensitivity_dbm=ont_sensitivity_dbm,
                           required_margin_db=required_margin_db)
    try:
        return optical_service.budget_report(db, project, phase, params)
    except OpticalError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc
