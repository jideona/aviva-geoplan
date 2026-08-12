from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import DbSession, require
from app.core.permissions import Permission
from app.schemas.features import ImportSummary
from app.services import import_service, project_service
from app.services.import_service import ImportError_
from app.services.project_service import ProjectError

router = APIRouter(prefix="/projects/{project_id}/imports", tags=["imports"])

# Imports run inline. At district scale (single-digit thousands of features)
# this completes in seconds. It moves to a Celery job before city-scale loads.
MAX_BYTES = 200 * 1024 * 1024


def _project(db, user, project_id: UUID):
    try:
        return project_service.get_project(db, user, project_id)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc


@router.post("/overture-buildings", response_model=ImportSummary)
async def import_overture(
    project_id: UUID,
    db: DbSession,
    file: UploadFile = File(...),
    user=Depends(require(Permission.GIS_IMPORT)),
) -> ImportSummary:
    """Import an Overture Maps buildings GeoJSON export.

    Overture arrives already deduplicated across its contributing datasets, so
    Google Open Buildings must not be imported separately against this load.
    """
    project = _project(db, user, project_id)
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail="File exceeds the 200 MB import limit.")
    try:
        result = import_service.import_overture_buildings(
            db, user, project, file.filename or "overture.geojson", data)
    except ImportError_ as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc
    return ImportSummary(**result.as_dict())


@router.post("/osm-roads", response_model=ImportSummary)
async def import_osm_roads(
    project_id: UUID,
    db: DbSession,
    file: UploadFile = File(...),
    user=Depends(require(Permission.GIS_IMPORT)),
) -> ImportSummary:
    """Import the road network from an OSM XML export.

    Supply the raw OSM XML, not an Overpass Turbo GeoJSON export — the GeoJSON
    export commonly filters to named roads and discards most of the network.
    """
    project = _project(db, user, project_id)
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail="File exceeds the 200 MB import limit.")
    try:
        result = import_service.import_osm_roads(
            db, user, project, file.filename or "map.osm", data)
    except ImportError_ as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc
    return ImportSummary(**result.as_dict())


@router.post("/streets", response_model=ImportSummary)
async def import_streets(
    project_id: UUID,
    db: DbSession,
    files: list[UploadFile] = File(...),
    user=Depends(require(Permission.GIS_IMPORT)),
) -> ImportSummary:
    """Import named street centrelines from one or more KML/KMZ files."""
    project = _project(db, user, project_id)
    payload = []
    for f in files:
        payload.append((f.filename or "street.kml", await f.read()))
    try:
        result = import_service.import_streets(db, user, project, payload)
    except ImportError_ as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc
    return ImportSummary(**result.as_dict())
