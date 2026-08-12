from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.services import project_service, routing_service
from app.services.project_service import ProjectError
from app.services.routing_service import RoutingError

router = APIRouter(prefix="/projects/{project_id}/routing", tags=["routing"])


@router.get("/phase/{phase}/geojson")
def routes_geojson(project_id: UUID, phase: int, db: DbSession,
                   user: CurrentUser) -> dict:
    """Feeder and distribution route geometry for the map."""
    if phase not in (1, 2):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Phase must be 1 or 2.")
    try:
        project = project_service.get_project(db, user, project_id)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc
    return routing_service.routes_geojson(db, project, phase)


@router.get("/noc.geojson")
def noc_geojson(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    """The NOC/OLT site as a permanent map feature — every feeder route starts
    here, so the map should always show it, routes on or off."""
    try:
        project_service.get_project(db, user, project_id)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc
    from app.services.pilot_service import NOC_LAT, NOC_LON
    return {"type": "FeatureCollection", "features": [{
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [NOC_LON, NOC_LAT]},
        "properties": {"kind": "noc", "name": "NOC / OLT"},
    }]}


@router.get("/ring/geojson")
def ring_geojson(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    """Feeder-ring resilience option: closed loop NOC → every FDH → NOC, with
    incremental quantities vs the as-designed feeder tree in `properties`."""
    try:
        project = project_service.get_project(db, user, project_id)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc
    try:
        return routing_service.feeder_ring(db, project)
    except RoutingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.get("/full/geojson")
def routes_full_geojson(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    """Feeder + distribution geometry for the WHOLE design — every FDH from the
    NOC and every FAT from its FDH, not just the pilot phases."""
    try:
        project = project_service.get_project(db, user, project_id)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc
    return routing_service.routes_geojson(db, project, None)


@router.get("/cable-core-schedule")
def cable_core_schedule(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    """Segment-by-segment fibre core count, feeder through distribution to
    drop — one row per physical cable run (NOC->FDH, FDH->FAT, FAT->building)
    with the cores and length each specific run needs. Feeder/distribution
    lengths are street-graph routed; drop lengths are straight-line estimates
    (same convention as the BOQ)."""
    try:
        project = project_service.get_project(db, user, project_id)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc
    try:
        return routing_service.cable_core_schedule(db, project)
    except RoutingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.get("/phase/{phase}")
def route_phase(project_id: UUID, phase: int, db: DbSession,
                user: CurrentUser) -> dict:
    """Route a pilot phase underground: feeder, distribution, trench, chambers
    and cable quantities. Phase 1 is the connectorised core."""
    if phase not in (1, 2):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Phase must be 1 or 2.")
    try:
        project = project_service.get_project(db, user, project_id)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc
    try:
        return routing_service.route_phase(db, project, phase)
    except RoutingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc
