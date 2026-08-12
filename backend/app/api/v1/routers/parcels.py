from uuid import UUID

from fastapi import (APIRouter, Body, Depends, File, HTTPException,
                     UploadFile, status)
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, require
from app.core.permissions import Permission
from app.db.models.parcel import Parcel
from app.services import parcel_service, project_service
from app.services.parcel_service import ParcelError
from app.services.project_service import ProjectError

router = APIRouter(prefix="/projects/{project_id}/parcels", tags=["parcels"])


def _project(db, user, project_id: UUID):
    try:
        return project_service.get_project(db, user, project_id)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc


@router.post("/perimeters")
async def import_perimeters(project_id: UUID, db: DbSession,
                            file: UploadFile = File(...),
                            user=Depends(require(Permission.GIS_IMPORT))) -> dict:
    """Import estate and compound perimeters from KML or KMZ."""
    project = _project(db, user, project_id)
    try:
        return parcel_service.import_perimeters(
            db, user, project, file.filename or "perimeters.kmz", await file.read())
    except ParcelError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.post("/markers")
async def import_markers(project_id: UUID, db: DbSession,
                         file: UploadFile = File(...),
                         user=Depends(require(Permission.GIS_IMPORT))) -> dict:
    """Import the per-building count markers dropped during the estate survey."""
    project = _project(db, user, project_id)
    try:
        return parcel_service.import_markers(
            db, user, project, file.filename or "markers.kmz", await file.read())
    except ParcelError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.post("/name-points")
async def import_name_points(project_id: UUID, db: DbSession,
                             file: UploadFile = File(...),
                             user=Depends(require(Permission.GIS_IMPORT))) -> dict:
    """Name parcels from labelled points dropped inside them."""
    project = _project(db, user, project_id)
    try:
        return parcel_service.import_name_points(
            db, user, project, file.filename or "names.kmz", await file.read())
    except ParcelError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.get("")
def listing(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    _project(db, user, project_id)
    return parcel_service.listing(db, project_id)


@router.post("/{parcel_id}/name")
def rename(project_id: UUID, parcel_id: UUID, db: DbSession,
           name: str = Body(..., embed=True),
           user=Depends(require(Permission.GIS_EDIT))) -> dict:
    project = _project(db, user, project_id)
    try:
        return parcel_service.rename_parcel(db, user, project, parcel_id, name)
    except ParcelError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.post("/attach-units")
def attach_units(project_id: UUID, db: DbSession,
                 user=Depends(require(Permission.GIS_EDIT))) -> dict:
    """Match workbook estate counts onto parcels and report disagreements."""
    project = _project(db, user, project_id)
    return parcel_service.attach_observed_units(db, user, project)


@router.get("/summary")
def summary(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    _project(db, user, project_id)
    return parcel_service.summary(db, project_id)


@router.get(".geojson")
def parcels_geojson(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    _project(db, user, project_id)
    features = []
    for p in db.scalars(select(Parcel).where(Parcel.project_id == project_id)):
        units = p.observed_units or p.declared_units
        features.append({
            "type": "Feature",
            "geometry": mapping(to_shape(p.geom)),
            "properties": {
                "parcel_id": str(p.id), "code": p.parcel_code, "name": p.name,
                "survey_code": p.survey_code,
                "area_sqm": float(p.area_sqm),
                "buildings": p.building_count, "markers": p.marker_count,
                "units": units,
                "has_units": units is not None,
            },
        })
    return {"type": "FeatureCollection", "features": features}
