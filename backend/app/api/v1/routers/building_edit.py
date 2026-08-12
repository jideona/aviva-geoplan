from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import DbSession, require
from app.core.permissions import Permission
from app.domain.building_edit import CaptureSource, rules_for
from app.services import building_edit_service, detection_service, project_service
from app.services.building_edit_service import BuildingEditError
from app.services.detection_service import DetectionError
from app.services.project_service import ProjectError

router = APIRouter(prefix="/projects/{project_id}/buildings", tags=["building edit"])


class CreateBuilding(BaseModel):
    geometry: dict
    source: str = "traced_reference"


class MoveBuilding(BaseModel):
    geometry: dict


class Exclude(BaseModel):
    excluded: bool = True
    reason: str | None = None


class BulkExclude(BaseModel):
    building_ids: list[UUID]
    reason: str | None = None


def _project(db, user, project_id):
    try:
        return project_service.get_project(db, user, project_id)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc


@router.get("/capture-sources")
def capture_sources() -> dict:
    return {"sources": [{"value": s.value, **rules_for(s)}
                        for s in CaptureSource]}


class Cleanup(BaseModel):
    min_area_sqm: float = 10.0
    max_circularity: float = 0.88
    dry_run: bool = True


@router.post("/cleanup")
def cleanup(project_id: UUID, payload: Cleanup, db: DbSession,
            user=Depends(require(Permission.BUILDING_EDIT))) -> dict:
    """Find/exclude non-building footprints (tiny slivers + round vegetation
    blobs). dry_run=true previews; false excludes them (reversible)."""
    project = _project(db, user, project_id)
    try:
        return building_edit_service.cleanup_noise(
            db, user, project, payload.min_area_sqm, payload.max_circularity,
            payload.dry_run)
    except BuildingEditError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


class DetectImport(BaseModel):
    geojson: dict
    overlap_threshold: float = 0.30
    dry_run: bool = False


@router.post("/detect-import")
def detect_import(project_id: UUID, payload: DetectImport, db: DbSession,
                  user=Depends(require(Permission.BUILDING_EDIT))) -> dict:
    """Ingest auto-detected footprints (from the offline Esri detector): dedupe
    against the register and import only new rooftops, tagged pilot-only. With
    dry_run=true it writes nothing and returns a preview instead."""
    project = _project(db, user, project_id)
    try:
        return detection_service.ingest_candidates(
            db, user, project, payload.geojson, payload.overlap_threshold,
            dry_run=payload.dry_run)
    except DetectionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.delete("/detected")
def clear_detected(project_id: UUID, db: DbSession,
                   user=Depends(require(Permission.BUILDING_EDIT))) -> dict:
    """Delete all Esri auto-detected buildings — the undo for a test import."""
    project = _project(db, user, project_id)
    return detection_service.clear_detected(db, user, project)


@router.post("")
def create(project_id: UUID, payload: CreateBuilding, db: DbSession,
           user=Depends(require(Permission.BUILDING_EDIT))) -> dict:
    project = _project(db, user, project_id)
    try:
        return building_edit_service.create_building(
            db, user, project, payload.geometry, payload.source)
    except BuildingEditError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.patch("/{building_id}/geometry")
def move(project_id: UUID, building_id: UUID, payload: MoveBuilding,
         db: DbSession, user=Depends(require(Permission.BUILDING_EDIT))) -> dict:
    project = _project(db, user, project_id)
    try:
        return building_edit_service.move_building(
            db, user, project, building_id, payload.geometry)
    except BuildingEditError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.patch("/{building_id}/exclude")
def exclude(project_id: UUID, building_id: UUID, payload: Exclude, db: DbSession,
            user=Depends(require(Permission.BUILDING_EDIT))) -> dict:
    """Exclude a non-serviceable building — hidden everywhere, but reversible."""
    project = _project(db, user, project_id)
    try:
        return building_edit_service.set_excluded(
            db, user, project, building_id, payload.excluded, payload.reason)
    except BuildingEditError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.post("/bulk-exclude")
def bulk_exclude(project_id: UUID, payload: BulkExclude, db: DbSession,
                 user=Depends(require(Permission.BUILDING_EDIT))) -> dict:
    project = _project(db, user, project_id)
    return building_edit_service.bulk_exclude(
        db, user, project, payload.building_ids, payload.reason)


@router.delete("/{building_id}")
def delete(project_id: UUID, building_id: UUID, db: DbSession,
           user=Depends(require(Permission.BUILDING_EDIT))) -> dict:
    project = _project(db, user, project_id)
    try:
        return building_edit_service.delete_building(db, user, project, building_id)
    except BuildingEditError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc
