"""Mobile field-survey API — manholes, media (MinIO) and a delta sync pull.

Designed for an offline-first client: every create takes a client-generated id
so replaying a queued capture on reconnect is idempotent, and /sync/changes
returns everything touched since a timestamp so the local cache can catch up.
Building / street / corridor edits reuse their existing routers; this module
adds the net-new surveyed asset (manhole) and the shared media pipeline.
"""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, DbSession, require, require_any
from app.core.permissions import Permission
from app.services import (building_edit_service, building_photo_service,
                          manhole_service, media_service, project_service,
                          survey_route_service)
from app.services.building_photo_service import BuildingPhotoError
from app.services.manhole_service import ManholeError
from app.services.media_service import MediaError
from app.services.project_service import ProjectError
from app.services.survey_route_service import SurveyRouteError

router = APIRouter(prefix="/projects/{project_id}/mobile", tags=["mobile survey"])


def _project(db, user, project_id):
    try:
        return project_service.get_project(db, user, project_id)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc


# ---- Manholes ------------------------------------------------------------- #
class CaptureManhole(BaseModel):
    lon: float
    lat: float
    manhole_type: str = "manhole"
    condition: str = "unknown"
    code: str | None = None
    condition_notes: str | None = None
    gps_accuracy_m: float | None = None
    client_id: str | None = None
    survey_session_id: UUID | None = None


class AssessManhole(BaseModel):
    condition: str | None = None
    condition_notes: str | None = None
    code: str | None = None
    lon: float | None = None
    lat: float | None = None


@router.post("/manholes")
def capture_manhole(project_id: UUID, payload: CaptureManhole, db: DbSession,
                    user=Depends(require(Permission.GIS_EDIT))) -> dict:
    project = _project(db, user, project_id)
    try:
        return manhole_service.create(
            db, user, project, lon=payload.lon, lat=payload.lat,
            manhole_type=payload.manhole_type, condition=payload.condition,
            code=payload.code, condition_notes=payload.condition_notes,
            gps_accuracy_m=payload.gps_accuracy_m, client_id=payload.client_id,
            survey_session_id=payload.survey_session_id)
    except ManholeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.patch("/manholes/{manhole_id}")
def assess_manhole(project_id: UUID, manhole_id: UUID, payload: AssessManhole,
                   db: DbSession, user=Depends(require(Permission.GIS_EDIT))) -> dict:
    project = _project(db, user, project_id)
    try:
        return manhole_service.update_condition(
            db, user, project, manhole_id, condition=payload.condition,
            condition_notes=payload.condition_notes, code=payload.code,
            lon=payload.lon, lat=payload.lat)
    except ManholeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.delete("/manholes/{manhole_id}")
def delete_manhole(project_id: UUID, manhole_id: UUID, db: DbSession,
                   user=Depends(require(Permission.GIS_EDIT))) -> dict:
    """Soft-delete (excluded=True) — see manhole_service.set_excluded."""
    project = _project(db, user, project_id)
    try:
        return manhole_service.set_excluded(db, user, project, manhole_id)
    except ManholeError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc


@router.get("/manholes.geojson")
def manholes_geojson(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    project = _project(db, user, project_id)
    return manhole_service.geojson(db, project)


# ---- Building photos (quick geotagged capture, no building lookup) -------- #
class CaptureBuildingPhoto(BaseModel):
    lon: float
    lat: float
    gps_accuracy_m: float | None = None
    client_id: str | None = None


@router.post("/building-photos")
def capture_building_photo(project_id: UUID, payload: CaptureBuildingPhoto, db: DbSession,
                           user=Depends(require(Permission.GIS_EDIT))) -> dict:
    project = _project(db, user, project_id)
    try:
        return building_photo_service.create(
            db, user, project, lon=payload.lon, lat=payload.lat,
            gps_accuracy_m=payload.gps_accuracy_m, client_id=payload.client_id)
    except BuildingPhotoError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.get("/building-photos.geojson")
def building_photos_geojson(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    project = _project(db, user, project_id)
    return building_photo_service.geojson(db, project)


# ---- Survey routes (as-walked cable paths) -------------------------------- #
class CaptureRoute(BaseModel):
    points: list                # [[lon,lat], ...] or [{"lon":..,"lat":..}, ...]
    route_type: str = "cable_route"
    code: str | None = None
    notes: str | None = None
    avg_accuracy_m: float | None = None
    client_id: str | None = None
    survey_session_id: UUID | None = None


@router.post("/routes")
def capture_route(project_id: UUID, payload: CaptureRoute, db: DbSession,
                  user=Depends(require(Permission.GIS_EDIT))) -> dict:
    project = _project(db, user, project_id)
    try:
        return survey_route_service.create(
            db, user, project, points=payload.points, route_type=payload.route_type,
            code=payload.code, notes=payload.notes,
            avg_accuracy_m=payload.avg_accuracy_m, client_id=payload.client_id,
            survey_session_id=payload.survey_session_id)
    except SurveyRouteError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.get("/routes.geojson")
def routes_geojson(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    project = _project(db, user, project_id)
    return survey_route_service.geojson(db, project)


# ---- Media (MinIO) -------------------------------------------------------- #
class RequestUpload(BaseModel):
    entity_type: str            # "manhole" | "building" | "street" | ...
    entity_id: UUID
    kind: str = "photo"         # "photo" | "video"
    content_type: str = "image/jpeg"
    client_id: str | None = None
    caption: str | None = None
    captured_lat: float | None = None
    captured_lon: float | None = None
    survey_session_id: UUID | None = None


class ConfirmUpload(BaseModel):
    size_bytes: int | None = None


@router.post("/media/request-upload")
def request_upload(project_id: UUID, payload: RequestUpload, db: DbSession,
                   user=Depends(require(Permission.GIS_EDIT))) -> dict:
    project = _project(db, user, project_id)
    try:
        return media_service.request_upload(
            db, user, project, entity_type=payload.entity_type,
            entity_id=payload.entity_id, kind=payload.kind,
            content_type=payload.content_type, client_id=payload.client_id,
            caption=payload.caption, captured_lat=payload.captured_lat,
            captured_lon=payload.captured_lon,
            survey_session_id=payload.survey_session_id)
    except MediaError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.post("/media/{media_id}/confirm")
def confirm_upload(project_id: UUID, media_id: UUID, payload: ConfirmUpload,
                   db: DbSession, user=Depends(require(Permission.GIS_EDIT))) -> dict:
    project = _project(db, user, project_id)
    try:
        return media_service.confirm_upload(db, user, project, media_id,
                                            size_bytes=payload.size_bytes)
    except MediaError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.get("/media")
def list_media(project_id: UUID, entity_type: str, entity_id: UUID,
               db: DbSession, user: CurrentUser) -> dict:
    project = _project(db, user, project_id)
    return {"media": media_service.list_for(db, project, entity_type, entity_id)}


# ---- Building field update (reuses existing service) ---------------------- #
class UpdateBuilding(BaseModel):
    building_type: str | None = None
    use_type: str | None = None
    address: str | None = None
    units_surveyed: int | None = None
    drop_deployment: str | None = None      # 'aerial' | 'underground'
    notes: str | None = None
    condition: str | None = None            # 'excellent' | 'good' | 'fair' | 'poor'
    # Full-replace list of linked manhole ids ("Associated Assets"); omit to
    # leave existing links untouched, pass [] to clear them.
    linked_manhole_ids: list[UUID] | None = None


class ExcludeBuilding(BaseModel):
    excluded: bool = True
    reason: str | None = None


@router.get("/buildings/near")
def buildings_near(project_id: UUID, lat: float, lon: float, db: DbSession,
                   user: CurrentUser, limit: int = Query(default=15, le=50)) -> dict:
    """Nearest buildings to a GPS point, for field selection."""
    project = _project(db, user, project_id)
    return {"buildings": building_edit_service.nearest(db, project, lat, lon, limit)}


@router.get("/manholes/near")
def manholes_near(project_id: UUID, lat: float, lon: float, db: DbSession,
                  user: CurrentUser, limit: int = Query(default=15, le=50)) -> dict:
    """Nearest manholes to a GPS point — for the Update Building screen's
    Associated Assets picker."""
    project = _project(db, user, project_id)
    return {"manholes": manhole_service.nearest(db, project, lat, lon, limit)}


@router.patch("/buildings/{building_id}")
def update_building(project_id: UUID, building_id: UUID, payload: UpdateBuilding,
                    db: DbSession,
                    user=Depends(require_any(Permission.BUILDING_EDIT,
                                             Permission.BUILDING_FIELD_UPDATE))) -> dict:
    project = _project(db, user, project_id)
    attrs = payload.model_dump(exclude_none=True, exclude={"linked_manhole_ids"})
    try:
        result = building_edit_service.update_attributes(
            db, user, project, building_id, attrs)
        if payload.linked_manhole_ids is not None:
            result.update(building_edit_service.link_manholes(
                db, user, project, building_id, payload.linked_manhole_ids))
        return result
    except Exception as exc:                            # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.patch("/buildings/{building_id}/exclude")
def exclude_building(project_id: UUID, building_id: UUID, payload: ExcludeBuilding,
                     db: DbSession,
                     user=Depends(require_any(Permission.BUILDING_EDIT,
                                              Permission.BUILDING_FIELD_UPDATE))) -> dict:
    """Flag a footprint the surveyor found does not exist on the ground (or
    restore one flagged in error). Reversible soft-delete — see
    building_edit_service.set_excluded; same mechanism the office map's
    "Remove building" action uses."""
    project = _project(db, user, project_id)
    try:
        return building_edit_service.set_excluded(
            db, user, project, building_id, payload.excluded, payload.reason)
    except Exception as exc:                            # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


# ---- Single-record server confirmation ------------------------------------ #
# So the field app can show "this reached the server" detail for one capture
# (per the office/field request to confirm images and coordinates actually
# arrived) without pulling a whole layer just to find one feature.
@router.get("/records/{kind}/{record_id}")
def record_detail(project_id: UUID, kind: str, record_id: UUID, db: DbSession,
                  user: CurrentUser) -> dict:
    from geoalchemy2.shape import to_shape

    project = _project(db, user, project_id)

    if kind == "manhole":
        from app.db.models.manhole import Manhole
        row = db.get(Manhole, record_id)
        if row is None or row.project_id != project.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
        p = to_shape(row.geom)
        return {"kind": "manhole", "lon": p.x, "lat": p.y, "code": row.code,
                "condition": row.condition, "surveyed_by": row.surveyed_by,
                "last_edited_by": row.last_edited_by,
                "verification_state": row.verification_state,
                "created_at": row.created_at.isoformat(),
                "updated_at": row.updated_at.isoformat()}

    if kind == "building_photo":
        from app.db.models.building_photo import BuildingPhoto
        row = db.get(BuildingPhoto, record_id)
        if row is None or row.project_id != project.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
        p = to_shape(row.geom)
        return {"kind": "building_photo", "lon": p.x, "lat": p.y,
                "surveyed_by": row.surveyed_by,
                "last_edited_by": row.last_edited_by,
                "verification_state": row.verification_state,
                "created_at": row.created_at.isoformat(),
                "updated_at": row.updated_at.isoformat()}

    if kind == "route":
        from app.db.models.survey_route import SurveyRoute
        row = db.get(SurveyRoute, record_id)
        if row is None or row.project_id != project.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
        return {"kind": "route", "route_type": row.route_type, "code": row.code,
                "length_m": float(row.length_m), "point_count": row.point_count,
                "surveyed_by": row.surveyed_by,
                "last_edited_by": row.last_edited_by,
                "created_at": row.created_at.isoformat(),
                "updated_at": row.updated_at.isoformat()}

    if kind == "building":
        from app.db.models.building import Building
        row = db.get(Building, record_id)
        if row is None or row.project_id != project.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
        return {"kind": "building", "code": row.building_code,
                "building_type": row.building_type, "address": row.address,
                "units_surveyed": row.units_surveyed,
                "drop_deployment": row.drop_deployment,
                "condition": row.condition,
                "linked_manholes": building_edit_service.linked_manholes(
                    db, project, row.id)["linked_manholes"],
                "last_edited_by": row.last_edited_by,
                "verification_state": row.verification_state,
                "updated_at": row.updated_at.isoformat()}

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Unknown record kind.")


# ---- Delta sync pull ------------------------------------------------------ #
@router.get("/sync/changes")
def sync_changes(project_id: UUID, db: DbSession, user: CurrentUser,
                 since: datetime | None = Query(default=None)) -> dict:
    """Everything touched since `since` (ISO 8601), so an offline cache can catch
    up. Omit `since` for a full pull."""
    project = _project(db, user, project_id)
    return {
        "server_time": datetime.utcnow().isoformat() + "Z",
        "manholes": manhole_service.geojson(db, project, since=since),
        "routes": survey_route_service.geojson(db, project, since=since),
        "building_photos": building_photo_service.geojson(db, project, since=since),
    }
