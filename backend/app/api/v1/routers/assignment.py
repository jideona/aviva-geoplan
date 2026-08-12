from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbSession, require
from app.core.permissions import Permission
from app.domain.street_assignment import AssignmentParams
from app.services import assignment_service, project_service
from app.services.project_service import ProjectError

router = APIRouter(prefix="/projects/{project_id}/street-assignment",
                   tags=["street assignment"])


class RunRequest(BaseModel):
    max_distance_m: float = Field(default=60.0, gt=0, le=500)
    only_unassigned: bool = True


class ReviewItem(BaseModel):
    building_id: UUID
    building_code: str | None
    street_id: UUID | None
    confidence: float | None
    distance_m: float | None
    reason: str | None
    footprint_area_sqm: float
    verification_state: str


def _project(db, user, project_id: UUID):
    try:
        return project_service.get_project(db, user, project_id)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc


@router.post("/run")
def run(project_id: UUID, db: DbSession, payload: RunRequest = Body(default=RunRequest()),
        user=Depends(require(Permission.GIS_EDIT))) -> dict:
    project = _project(db, user, project_id)
    return assignment_service.run_assignment(
        db, user, project,
        AssignmentParams(max_distance_m=payload.max_distance_m),
        only_unassigned=payload.only_unassigned,
    )


@router.get("/review", response_model=list[ReviewItem])
def review(project_id: UUID, db: DbSession, user: CurrentUser,
           limit: int = 200) -> list[ReviewItem]:
    _project(db, user, project_id)
    return [
        ReviewItem(
            building_id=b.id, building_code=b.building_code, street_id=b.street_id,
            confidence=(float(b.street_assignment_confidence)
                        if b.street_assignment_confidence is not None else None),
            distance_m=(float(b.street_assignment_distance_m)
                        if b.street_assignment_distance_m is not None else None),
            reason=b.street_assignment_reason,
            footprint_area_sqm=float(b.footprint_area_sqm),
            verification_state=b.verification_state,
        )
        for b in assignment_service.review_queue(db, project_id, limit)
    ]


@router.post("/buildings/{building_id}")
def reassign(project_id: UUID, building_id: UUID, db: DbSession,
             street_id: UUID | None = Body(default=None, embed=True),
             user=Depends(require(Permission.BUILDING_EDIT))) -> dict:
    project = _project(db, user, project_id)
    try:
        b = assignment_service.reassign(db, user, project, building_id, street_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc
    return {"building_id": str(b.id), "street_id": str(b.street_id) if b.street_id else None,
            "verification_state": b.verification_state}


@router.get("/naming-queue")
def naming_queue(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    """Unnamed roads ranked by dependent buildings — the field naming worklist."""
    _project(db, user, project_id)
    rows = assignment_service.naming_queue(db, project_id)
    return {
        "unnamed_streets": len(rows),
        "buildings_affected": sum(r["building_count"] for r in rows),
        "streets": rows,
    }
