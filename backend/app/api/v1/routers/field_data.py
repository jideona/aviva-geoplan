from datetime import date, datetime
from uuid import UUID

from fastapi import (APIRouter, Body, Depends, File, Form, HTTPException,
                     Query, UploadFile, status)

from app.api.deps import CurrentUser, DbSession, require
from app.core.permissions import Permission
from app.services import field_activity_service, field_data_service, project_service
from app.services.field_data_service import FieldDataError
from app.services.project_service import ProjectError

router = APIRouter(prefix="/projects/{project_id}/field-data", tags=["field data"])


def _project(db, user, project_id: UUID):
    try:
        return project_service.get_project(db, user, project_id)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc


@router.post("/import")
async def import_workbook(
    project_id: UUID,
    db: DbSession,
    file: UploadFile = File(...),
    survey_date: date | None = Form(default=None),
    surveyor: str | None = Form(default=None),
    user=Depends(require(Permission.GIS_IMPORT)),
) -> dict:
    """Import an Aviva route-analysis workbook: recorded street names and
    observed premises counts."""
    project = _project(db, user, project_id)
    try:
        return field_data_service.import_workbook(
            db, user, project, file.filename or "route_analysis.xlsx",
            await file.read(), survey_date, surveyor)
    except FieldDataError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.get("/streets")
def matching_queue(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    """Recorded street names and how many are still awaiting a geometry match."""
    _project(db, user, project_id)
    return field_data_service.matching_queue(db, project_id)


@router.get("/streets/{recorded_id}/candidates")
def candidates(project_id: UUID, recorded_id: UUID, db: DbSession,
               user: CurrentUser, tolerance: float = 0.25) -> dict:
    project = _project(db, user, project_id)
    try:
        return field_data_service.candidates(db, project, recorded_id, tolerance)
    except FieldDataError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc


@router.post("/streets/{recorded_id}/match")
def confirm_match(project_id: UUID, recorded_id: UUID, db: DbSession,
                  street_id: UUID = Body(..., embed=True),
                  user=Depends(require(Permission.GIS_EDIT))) -> dict:
    project = _project(db, user, project_id)
    try:
        return field_data_service.confirm_match(
            db, user, project, recorded_id, street_id)
    except FieldDataError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.get("/estates")
def estates(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    """Estates that can be located from street names, and those that cannot.

    Each pending estate is a block of observed unit counts waiting on one
    street name.
    """
    project = _project(db, user, project_id)
    return field_data_service.estate_worklist(db, project)


@router.get("/premises-model")
def premises_model(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    """The premises estimation model fitted on observed unit counts, with an
    explicit statement of whether the sample supports a district total."""
    project = _project(db, user, project_id)
    return field_data_service.build_model(db, project)


# ---- Field activity feed (manager view) ------------------------------------ #
@router.get("/activity")
def activity(
    project_id: UUID, db: DbSession,
    user=Depends(require(Permission.FIELD_ACTIVITY_VIEW)),
    surveyor: str | None = None,
    entity_type: str | None = None,
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = 0,
) -> dict:
    """Reverse-chronological feed of field captures and edits (buildings,
    manholes, building photos, survey routes, uploaded media), so a manager in
    the office can confirm data is actually arriving from the field, see who
    sent what and when, and tell a brand-new record from one that was just
    modified. A read model over the append-only audit trail (SRD FR-AUD-001)."""
    project = _project(db, user, project_id)
    return field_activity_service.feed(
        db, project, surveyor=surveyor, entity_type=entity_type,
        since=since, until=until, limit=limit, offset=offset)


@router.get("/activity/surveyors")
def activity_surveyors(project_id: UUID, db: DbSession,
                       user=Depends(require(Permission.FIELD_ACTIVITY_VIEW))) -> dict:
    """Distinct surveyors with field activity on this project, for a filter."""
    project = _project(db, user, project_id)
    return {"surveyors": field_activity_service.surveyors(db, project)}
