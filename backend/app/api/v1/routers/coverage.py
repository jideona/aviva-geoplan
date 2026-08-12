from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import CurrentUser, DbSession, require
from app.core.permissions import Permission
from app.services import (coverage_export, coverage_service, project_service)
from app.services.coverage_service import CoverageError
from app.services.project_service import ProjectError

router = APIRouter(prefix="/projects/{project_id}/coverage", tags=["coverage"])


def _project(db, user, project_id: UUID):
    try:
        return project_service.get_project(db, user, project_id)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc


@router.get("")
def coverage(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    """FAT service-area coverage and property-density report.

    Confirmed data (surveyed parcels) and estimated data (inferred from
    footprint geometry) are reported separately and never merged.
    """
    project = _project(db, user, project_id)
    try:
        return coverage_service.build_report(db, project)
    except CoverageError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.get("/report.xlsx")
def coverage_xlsx(project_id: UUID, db: DbSession,
                  user=Depends(require(Permission.EXPORT))) -> Response:
    project = _project(db, user, project_id)
    try:
        report = coverage_service.build_report(db, project)
    except CoverageError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc
    data = coverage_export.build_workbook(report)
    name = f"{project.code_prefix.lower()}_fat_coverage_report.xlsx"
    return Response(
        content=data,
        media_type=("application/vnd.openxmlformats-officedocument"
                    ".spreadsheetml.sheet"),
        headers={"Content-Disposition": f'attachment; filename="{name}"'})
