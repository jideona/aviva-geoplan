from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, DbSession, require
from app.core.permissions import Permission
from app.domain.attribution import ExportPurpose
from app.services import export_service, project_service, register_service
from app.services.export_service import ExportBlocked
from app.services.project_service import ProjectError
from app.services.register_service import RegisterFilter

router = APIRouter(prefix="/projects/{project_id}/register", tags=["register"])


class RegisterRow(BaseModel):
    id: UUID
    building_code: str | None
    street_code: str | None
    street_name: str | None
    footprint_area_sqm: float
    building_type: str
    use_type: str
    floors_reported: int | None
    units_surveyed: int | None
    premises_estimated: int | None
    assignment_confidence: float | None
    assignment_distance_m: float | None
    assignment_reason: str | None
    source_dataset: str | None
    licence_class: str
    verification_state: str
    survey_status: str


class RegisterPage(BaseModel):
    total: int
    limit: int
    offset: int
    filter_description: str
    rows: list[RegisterRow]


def _project(db, user, project_id: UUID):
    try:
        return project_service.get_project(db, user, project_id)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc


def _filter(
    street_id: UUID | None = None,
    verification_state: str | None = None,
    building_type: str | None = None,
    use_type: str | None = None,
    licence_class: str | None = None,
    unassigned_only: bool = False,
    needs_review: bool = False,
    min_area: float | None = None,
    max_area: float | None = None,
    search: str | None = None,
) -> RegisterFilter:
    return RegisterFilter(street_id, verification_state, building_type, use_type,
                          licence_class, unassigned_only, needs_review,
                          min_area, max_area, search)


@router.get("", response_model=RegisterPage)
def list_register(
    project_id: UUID, db: DbSession, user: CurrentUser,
    f: RegisterFilter = Depends(_filter),
    sort: str = "area", descending: bool = True,
    limit: int = Query(100, le=1000), offset: int = 0,
) -> RegisterPage:
    _project(db, user, project_id)
    rows = register_service.query(db, project_id, f, sort, descending, limit, offset)
    return RegisterPage(
        total=register_service.count(db, project_id, f),
        limit=limit, offset=offset, filter_description=f.describe(),
        rows=[
            RegisterRow(
                id=b.id, building_code=b.building_code, street_code=street_code,
                street_name=street_name,
                footprint_area_sqm=float(b.footprint_area_sqm),
                building_type=b.building_type, use_type=b.use_type,
                floors_reported=b.floors_reported, units_surveyed=b.units_surveyed,
                premises_estimated=b.premises_estimated,
                assignment_confidence=(float(b.street_assignment_confidence)
                                       if b.street_assignment_confidence is not None
                                       else None),
                assignment_distance_m=(float(b.street_assignment_distance_m)
                                       if b.street_assignment_distance_m is not None
                                       else None),
                assignment_reason=b.street_assignment_reason,
                source_dataset=b.source_dataset, licence_class=b.licence_class,
                verification_state=b.verification_state,
                survey_status=b.survey_status,
            )
            for b, street_name, street_code in rows
        ],
    )


@router.get("/summary")
def summary(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    _project(db, user, project_id)
    return register_service.summary(db, project_id)


@router.get("/attribution")
def attribution(project_id: UUID, db: DbSession, user: CurrentUser,
                purpose: ExportPurpose = ExportPurpose.INTERNAL) -> dict:
    """What this register is built from, and whether it may be exported for
    the stated purpose."""
    project = _project(db, user, project_id)
    m = export_service.manifest(db, project, purpose)
    return {"project": m.project, "generated": m.generated,
            "purpose": m.purpose.value, "blocked": m.blocked, "reason": m.reason,
            "attribution": m.attribution_lines(),
            "sources": [{"name": s.name, "licence": s.licence,
                         "licence_class": s.licence_class,
                         "feature_count": s.feature_count} for s in m.sources]}


def _export(fn, media: str, filename: str):
    def handler(project_id: UUID, db: DbSession,
                f: RegisterFilter = Depends(_filter),
                purpose: ExportPurpose = ExportPurpose.INTERNAL,
                user=Depends(require(Permission.EXPORT))):
        project = _project(db, user, project_id)
        try:
            payload = fn(db, user, project, f, purpose)
        except ExportBlocked as exc:
            # 451: the request is refused for legal rather than technical reasons.
            raise HTTPException(status_code=451, detail=str(exc)) from exc
        data = payload.encode("utf-8") if isinstance(payload, str) else payload
        stamp = project.code_prefix.lower()
        return Response(content=data, media_type=media, headers={
            "Content-Disposition": f'attachment; filename="{stamp}_{filename}"'})
    return handler


router.add_api_route("/export.csv", _export(
    export_service.to_csv, "text/csv", "building_register.csv"), methods=["GET"])
router.add_api_route("/export.xlsx", _export(
    export_service.to_xlsx,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "building_register.xlsx"), methods=["GET"])
router.add_api_route("/export.geojson", _export(
    export_service.to_geojson, "application/geo+json",
    "building_register.geojson"), methods=["GET"])
