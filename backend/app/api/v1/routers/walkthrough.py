from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import CurrentUser, DbSession, require
from app.core.permissions import Permission
from app.services import (export_service, project_service, walkthrough_service)
from app.services.project_service import ProjectError

router = APIRouter(prefix="/projects/{project_id}/walkthrough", tags=["walkthrough"])


def _project(db, user, project_id: UUID):
    try:
        return project_service.get_project(db, user, project_id)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc


@router.get("/currency")
def currency(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    """How old the evidence behind this register is."""
    _project(db, user, project_id)
    return walkthrough_service.currency_report(db, project_id)


@router.get("/grid")
def grid(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    """Survey areas ranked by how stale their data is."""
    project = _project(db, user, project_id)
    return walkthrough_service.survey_grid(db, project)


@router.get("/coverage")
def coverage(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    """Where unit counts have been observed, and where they have not."""
    project = _project(db, user, project_id)
    return walkthrough_service.survey_coverage(db, project)


@router.get("/naming")
def naming(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    _project(db, user, project_id)
    rows = walkthrough_service.naming_worklist(db, project_id)
    return {"streets": rows, "count": len(rows),
            "buildings_depending": sum(r["buildings_depending"] for r in rows)}


@router.get("/pack.xlsx")
def pack(project_id: UUID, db: DbSession,
         user=Depends(require(Permission.EXPORT))) -> Response:
    """The field pack. Internal work instruction — no commercial licence gate."""
    project = _project(db, user, project_id)
    data = export_service.walkthrough_pack(db, user, project)
    name = f"{project.code_prefix.lower()}_walkthrough_pack.xlsx"
    return Response(
        content=data,
        media_type=("application/vnd.openxmlformats-officedocument"
                    ".spreadsheetml.sheet"),
        headers={"Content-Disposition": f'attachment; filename="{name}"'})
