import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import func, select
from sqlalchemy.exc import ProgrammingError

from datetime import datetime, timezone

from app.api.deps import CurrentUser, DbSession
from app.db.models.building import Building
from app.db.models.street import Street
from app.schemas.features import (BuildingOut, FeatureCollection, LicenceSummary,
                                  StreetOut)
from app.domain.currency import age_years, classify
from app.domain.verification import is_protected
from app.services import import_service, project_service
from app.services.project_service import ProjectError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}", tags=["features"])

# Guard against an unbounded map payload. Vector tiling replaces this when the
# register outgrows what a browser will accept as GeoJSON.
MAX_MAP_FEATURES = 20000


def _guard(db, user, project_id: UUID):
    try:
        return project_service.get_project(db, user, project_id)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc


@router.get("/buildings", response_model=list[BuildingOut])
def list_buildings(
    project_id: UUID, db: DbSession, user: CurrentUser,
    street_id: UUID | None = None,
    verification_state: str | None = None,
    unassigned: bool = False,
    limit: int = Query(200, le=2000), offset: int = 0,
) -> list[BuildingOut]:
    _guard(db, user, project_id)
    stmt = (select(Building, Street.name)
            .outerjoin(Street, Building.street_id == Street.id)
            .where(Building.project_id == project_id))
    if street_id:
        stmt = stmt.where(Building.street_id == street_id)
    if verification_state:
        stmt = stmt.where(Building.verification_state == verification_state)
    if unassigned:
        stmt = stmt.where(Building.street_id.is_(None))
    stmt = stmt.order_by(Building.footprint_area_sqm.desc()).limit(limit).offset(offset)

    out = []
    for b, street_name in db.execute(stmt).all():
        out.append(BuildingOut(
            id=b.id, building_code=b.building_code, street_id=b.street_id,
            street_name=street_name, footprint_area_sqm=float(b.footprint_area_sqm),
            building_type=b.building_type, use_type=b.use_type,
            floors_reported=b.floors_reported, premises_estimated=b.premises_estimated,
            units_surveyed=b.units_surveyed, source_dataset=b.source_dataset,
            licence_class=b.licence_class, verification_state=b.verification_state,
            survey_status=b.survey_status,
        ))
    return out


@router.get("/buildings.geojson", response_model=FeatureCollection)
def buildings_geojson(project_id: UUID, db: DbSession,
                      user: CurrentUser) -> FeatureCollection:
    _guard(db, user, project_id)
    try:
        count = db.scalar(select(func.count()).select_from(Building)
                          .where(Building.project_id == project_id,
                                 Building.excluded.is_(False))) or 0
    except ProgrammingError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The database schema is behind the application. Run "
                   "`make migrate`, then reload.") from exc
    if count > MAX_MAP_FEATURES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(f"{count:,} buildings exceeds the {MAX_MAP_FEATURES:,} GeoJSON "
                    "limit. Vector tiling is required at this scale."),
        )
    today = datetime.now(timezone.utc).date()
    from app.db.models.design import ServingZone as _SZ
    zone_code = {z.id: z.zone_code for z in db.scalars(
        select(_SZ).where(_SZ.project_id == project_id))}
    features = []
    try:
        rows = list(db.scalars(select(Building).where(
            Building.project_id == project_id, Building.excluded.is_(False))))
    except ProgrammingError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The database schema is behind the application. Run "
                   "`make migrate`, then reload.") from exc
    skipped = 0
    for b in rows:
        # One malformed row (e.g. a null area on a bad import) must not blank
        # the entire buildings layer — skip and log it, return the rest.
        try:
            features.append({
                "type": "Feature",
                "id": str(b.id),
                "geometry": mapping(to_shape(b.geom)),
                "properties": {
                    # MapLibre drops non-numeric feature ids on rendered
                    # features, so the UUID must also travel as a property for
                    # click-to-select tools (Remove building).
                    "building_id": str(b.id),
                    "area": float(b.footprint_area_sqm)
                    if b.footprint_area_sqm is not None else None,
                    "dataset": b.source_dataset,
                    "licence_class": b.licence_class,
                    "verification_state": b.verification_state,
                    "assigned": b.street_id is not None,
                    "source_age_years": age_years(b.source_update_date, today),
                    "currency": classify(b.source_update_date, today).value,
                    "serving_fat": zone_code.get(b.serving_zone_id),
                    "code": b.building_code,
                },
            })
        except Exception:  # noqa: BLE001 — deliberately defensive per-feature
            skipped += 1
            logger.exception("Skipped building %s in buildings.geojson", b.id)
    if skipped:
        logger.warning("buildings.geojson skipped %d malformed rows", skipped)
    return FeatureCollection(features=features)


@router.get("/fat-schedule")
def fat_schedule(project_id: UUID, db: DbSession, user: CurrentUser) -> dict:
    """Which buildings each FAT serves — the coverage confirmation list."""
    _guard(db, user, project_id)
    from app.db.models.design import DesignRun, ServingZone as _SZ
    run = db.scalar(select(DesignRun).where(
        DesignRun.project_id == project_id, DesignRun.is_current.is_(True)))
    if run is None:
        return {"fats": [], "note": "Run a design first."}
    zones = {z.id: z for z in db.scalars(
        select(_SZ).where(_SZ.design_run_id == run.id))}
    by_zone: dict = {}
    for b in db.scalars(select(Building).where(
            Building.project_id == project_id,
            Building.serving_zone_id.isnot(None))):
        by_zone.setdefault(b.serving_zone_id, []).append(b)
    out = []
    for zid, blds in by_zone.items():
        z = zones.get(zid)
        if z is None:
            continue
        blds.sort(key=lambda b: b.building_code or "")
        out.append({
            "fat_code": z.zone_code,
            "premises": z.premises_count,
            "buildings": [{
                "code": b.building_code,
                "area_sqm": float(b.footprint_area_sqm),
                "units": b.units_surveyed or b.premises_estimated,
                "type": b.building_type,
                "verification": b.verification_state,
            } for b in blds],
        })
    out.sort(key=lambda r: r["fat_code"])
    return {"fats": out, "count": len(out),
            "note": "Building codes carry their FAT: WUY-FAT-007-B03 is the "
                    "third building on FAT-007."}


@router.get("/streets", response_model=list[StreetOut])
def list_streets(project_id: UUID, db: DbSession, user: CurrentUser) -> list[StreetOut]:
    _guard(db, user, project_id)
    counts = dict(db.execute(
        select(Building.street_id, func.count())
        .where(Building.project_id == project_id, Building.street_id.isnot(None))
        .group_by(Building.street_id)
    ).all())
    streets = db.scalars(select(Street).where(Street.project_id == project_id)
                         .order_by(Street.street_code))
    return [
        StreetOut(id=s.id, street_code=s.street_code, name=s.name,
                  name_state=("unnamed" if s.name is None
                              else "confirmed" if is_protected(s.verification_state)
                              else "identified"),
                  name_source=s.name_source,
                  length_m=float(s.length_m), road_class=s.road_class,
                  licence_class=s.licence_class,
                  verification_state=s.verification_state,
                  building_count=counts.get(s.id, 0))
        for s in streets
    ]


@router.get("/streets.geojson", response_model=FeatureCollection)
def streets_geojson(project_id: UUID, db: DbSession,
                    user: CurrentUser) -> FeatureCollection:
    _guard(db, user, project_id)
    features = []
    skipped = 0
    for s in db.scalars(select(Street).where(Street.project_id == project_id)):
      try:
        features.append({
            "type": "Feature",
            "id": str(s.id),
            "geometry": mapping(to_shape(s.geom)),
            "properties": {
                # Carried in properties as well as the feature id: MapLibre does
                # not reliably surface string feature ids to click handlers.
                "street_id": str(s.id),
                "code": s.street_code,
                "name": s.name,
                # What to render on the map: the real name where one exists,
                # the provisional code where it does not, so every road is
                # identifiable while naming is outstanding.
                "label": s.name or s.street_code,
                "named": s.name is not None,
                # Three states, because a name OSM happened to carry is not
                # the same claim as one a surveyor stood in front of.
                #   confirmed  — field survey, photograph or naming authority
                #   identified — imported, plausible, unverified
                #   unnamed    — outstanding
                "name_state": (
                    "unnamed" if s.name is None
                    else "confirmed" if is_protected(s.verification_state)
                    else "identified"),
                "name_source": s.name_source,
                "verification_state": s.verification_state,
                "road_class": s.road_class,
                "length_m": float(s.length_m),
            },
        })
      except Exception:  # noqa: BLE001 — defensive per-feature
        skipped += 1
        logger.exception("Skipped street %s in streets.geojson", s.id)
    if skipped:
        logger.warning("streets.geojson skipped %d malformed rows", skipped)
    return FeatureCollection(features=features)


@router.get("/licence-summary", response_model=LicenceSummary)
def licence_summary(project_id: UUID, db: DbSession,
                    user: CurrentUser) -> LicenceSummary:
    _guard(db, user, project_id)
    return LicenceSummary(**import_service.licence_summary(db, project_id))
