from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import CurrentUser, DbSession, require
from app.core.permissions import Permission
from app.services import pilot_export, pilot_service, project_service
from app.services.pilot_service import PilotError
from app.services.project_service import ProjectError

router = APIRouter(prefix="/projects/{project_id}/pilot", tags=["pilot"])


def _project(db, user, project_id: UUID):
    try:
        return project_service.get_project(db, user, project_id)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc


@router.get("")
def pilot(project_id: UUID, db: DbSession, user: CurrentUser,
          olt_pon_ports: int = 16) -> dict:
    """The buildable pilot: connectorised core plus conventional extension,
    with equipment schedule, bounded by the OLT and stock."""
    project = _project(db, user, project_id)
    try:
        return pilot_service.build(db, project, olt_pon_ports)
    except PilotError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.get("/pack.xlsx")
def pilot_pack(project_id: UUID, db: DbSession,
               olt_pon_ports: int = 16,
               user=Depends(require(Permission.EXPORT))) -> Response:
    project = _project(db, user, project_id)
    try:
        plan = pilot_service.build(db, project, olt_pon_ports)
    except PilotError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc
    data = pilot_export.build_workbook(plan, project.name)
    name = f"{project.code_prefix.lower()}_pilot_design_pack.xlsx"
    return Response(content=data,
        media_type=("application/vnd.openxmlformats-officedocument"
                    ".spreadsheetml.sheet"),
        headers={"Content-Disposition": f'attachment; filename="{name}"'})
