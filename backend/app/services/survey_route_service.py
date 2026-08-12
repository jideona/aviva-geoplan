"""As-walked survey routes captured by the mobile app.

The app logs a list of GPS points as the surveyor walks a route; this stores the
polyline, measures it in the project metric CRS, and tags it field_surveyed.
Creates are idempotent by client_id so a queued offline capture replayed on
reconnect never duplicates.
"""
import uuid

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import LineString, mapping
from shapely.ops import transform
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.project import Project
from app.db.models.survey_route import ROUTE_TYPES, SurveyRoute
from app.db.models.user import User
from app.domain.crs import STORAGE_EPSG, _transformer
from app.services import audit_service

MIN_POINTS = 2
MIN_LENGTH_M = 2.0


class SurveyRouteError(ValueError):
    """Message is safe to show the user."""


def create(db: Session, user: User, project: Project, *, points: list,
           route_type: str = "cable_route", code: str | None = None,
           notes: str | None = None, avg_accuracy_m: float | None = None,
           client_id: str | None = None, survey_session_id: uuid.UUID | None = None
           ) -> dict:
    if route_type not in ROUTE_TYPES:
        raise SurveyRouteError(f"route_type must be one of {', '.join(ROUTE_TYPES)}.")
    # Accept [[lon,lat],...] or [{"lon":..,"lat":..},...]
    coords = []
    for p in points or []:
        if isinstance(p, dict):
            coords.append((float(p["lon"]), float(p["lat"])))
        else:
            coords.append((float(p[0]), float(p[1])))
    # Drop consecutive duplicates.
    clean = [coords[0]] if coords else []
    for c in coords[1:]:
        if c != clean[-1]:
            clean.append(c)
    if len(clean) < MIN_POINTS:
        raise SurveyRouteError("A route needs at least two distinct points.")

    if client_id:
        existing = db.scalar(select(SurveyRoute).where(
            SurveyRoute.project_id == project.id,
            SurveyRoute.client_id == client_id))
        if existing is not None:
            return _out(existing)

    line = LineString(clean)
    to_metric = _transformer(STORAGE_EPSG, project.metric_crs_epsg).transform
    length = transform(to_metric, line).length
    if length < MIN_LENGTH_M:
        raise SurveyRouteError(f"Route is only {length:.0f} m — too short to record.")

    row = SurveyRoute(
        project_id=project.id, client_id=client_id, code=code,
        route_type=route_type, geom=from_shape(line, srid=4326),
        length_m=round(length, 2), point_count=len(clean),
        avg_accuracy_m=avg_accuracy_m, notes=notes, surveyed_by=user.email,
        survey_session_id=survey_session_id, licence_class="owned",
        verification_state="field_observed")
    db.add(row)
    db.flush()
    audit_service.record(db, actor=user, entity_type="survey_route",
                         entity_id=row.id, action="capture_route",
                         project_id=project.id,
                         changes={"length_m": {"before": None, "after": round(length, 1)}})
    db.commit()
    db.refresh(row)
    return _out(row)


def geojson(db: Session, project: Project, since=None) -> dict:
    q = select(SurveyRoute).where(SurveyRoute.project_id == project.id,
                                  SurveyRoute.excluded.is_(False))
    if since is not None:
        q = q.where(SurveyRoute.updated_at > since)
    features = [{
        "type": "Feature", "geometry": mapping(to_shape(r.geom)),
        "properties": {"id": str(r.id), "code": r.code, "type": r.route_type,
                       "length_m": float(r.length_m), "points": r.point_count,
                       "surveyed_by": r.surveyed_by,
                       "updated_at": r.updated_at.isoformat()}}
        for r in db.scalars(q)]
    return {"type": "FeatureCollection", "features": features}


def _out(r: SurveyRoute) -> dict:
    return {"id": str(r.id), "client_id": r.client_id, "code": r.code,
            "route_type": r.route_type, "length_m": float(r.length_m),
            "point_count": r.point_count,
            "verification_state": r.verification_state,
            "updated_at": r.updated_at.isoformat()}
