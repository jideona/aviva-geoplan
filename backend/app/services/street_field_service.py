"""Field capture/update workflow for roads and streets.

This service is deliberately separate from naming_service: naming_service owns
licensed/desk naming semantics, while this module owns field-observed road
attributes and field verification from the Survey PWA.  Existing imported
streets are preferred; creating a new street is available only when no existing
geometry matches the real road on site.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import LineString, MultiLineString, mapping
from shapely.ops import transform
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.project import Project
from app.db.models.street import ROAD_CLASSES, Street
from app.db.models.user import User
from app.domain.crs import STORAGE_EPSG, _transformer
from app.services import audit_service

SURFACES = ("asphalt", "concrete", "paving", "compacted_earth", "unpaved", "unknown")
CONDITIONS = ("good", "fair", "poor", "impassable", "unknown")
ACCESS = ("public", "gated", "restricted", "private", "unknown")


class StreetFieldError(ValueError):
    """Message is safe to show to a field user."""


def _validate(attrs: dict) -> None:
    if attrs.get("road_class") is not None and attrs["road_class"] not in ROAD_CLASSES:
        raise StreetFieldError(f"road_class must be one of {', '.join(ROAD_CLASSES)}.")
    if attrs.get("surface") is not None and attrs["surface"] not in SURFACES:
        raise StreetFieldError(f"surface must be one of {', '.join(SURFACES)}.")
    if attrs.get("condition") is not None and attrs["condition"] not in CONDITIONS:
        raise StreetFieldError(f"condition must be one of {', '.join(CONDITIONS)}.")
    if attrs.get("access") is not None and attrs["access"] not in ACCESS:
        raise StreetFieldError(f"access must be one of {', '.join(ACCESS)}.")
    if attrs.get("width_m") is not None:
        width = float(attrs["width_m"])
        if not 0.5 <= width <= 100:
            raise StreetFieldError("width_m must be between 0.5 m and 100 m.")
    if attrs.get("name") is not None and len(str(attrs["name"]).strip()) < 2:
        raise StreetFieldError("A street name must be at least two characters.")


def nearest(db: Session, project: Project, lat: float, lon: float,
            limit: int = 15) -> list[dict]:
    pt = func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)
    dist = func.ST_DistanceSphere(Street.geom, pt)
    rows = db.execute(
        select(Street, dist.label("dist"))
        .where(Street.project_id == project.id)
        .order_by(dist).limit(limit)).all()
    return [{
        "id": str(s.id), "code": s.street_code, "name": s.name,
        "road_class": s.road_class, "surface": s.surface,
        "condition": s.condition, "access": s.access,
        "width_m": float(s.width_m) if s.width_m is not None else None,
        "verification_state": s.verification_state,
        "surveyed_by": s.surveyed_by, "last_edited_by": s.last_edited_by,
        "distance_m": round(float(d), 1),
    } for s, d in rows]


def update(db: Session, user: User, project: Project, street_id: uuid.UUID,
           attrs: dict) -> dict:
    street = db.scalar(select(Street).where(
        Street.id == street_id, Street.project_id == project.id))
    if street is None:
        raise StreetFieldError("Street not found.")
    _validate(attrs)

    before: dict = {}
    fields = ("road_class", "surface", "condition", "access", "width_m", "field_notes")
    for field in fields:
        if field in attrs:
            before[field] = getattr(street, field)
            setattr(street, field, attrs[field])

    if "name" in attrs and attrs["name"] is not None:
        value = str(attrs["name"]).strip()
        before["name"] = street.name
        street.name = value
        street.name_status = "named"
        street.name_source = "field_observed"
        street.name_recorded_by = user.email
        street.needs_field_name = False

    # First field verification preserves who originally surveyed it; later
    # changes preserve that fact and only advance last_edited_by.
    if not street.surveyed_by:
        street.surveyed_by = user.email
        street.assessed_at = datetime.now(timezone.utc)
    else:
        street.last_edited_by = user.email
    street.verification_state = "field_observed"

    after = {k: getattr(street, k) for k in before}
    audit_service.record(db, actor=user, entity_type="street", entity_id=street.id,
                         action="field_verify_street", project_id=project.id,
                         changes=audit_service.diff(before, after))
    db.commit()
    db.refresh(street)
    return _out(street)


def create(db: Session, user: User, project: Project, *, points: list,
           name: str | None = None, road_class: str = "unknown",
           surface: str = "unknown", condition: str = "unknown",
           access: str = "unknown", width_m: float | None = None,
           field_notes: str | None = None, client_id: str | None = None) -> dict:
    attrs = {"name": name, "road_class": road_class, "surface": surface,
             "condition": condition, "access": access, "width_m": width_m}
    _validate(attrs)
    coords: list[tuple[float, float]] = []
    for p in points or []:
        if isinstance(p, dict):
            coords.append((float(p["lon"]), float(p["lat"])))
        else:
            coords.append((float(p[0]), float(p[1])))
    clean = [coords[0]] if coords else []
    for c in coords[1:]:
        if c != clean[-1]:
            clean.append(c)
    if len(clean) < 2:
        raise StreetFieldError("A new road needs at least two distinct GPS points.")

    if client_id:
        existing = db.scalar(select(Street).where(
            Street.project_id == project.id, Street.field_client_id == client_id))
        if existing is not None:
            return _out(existing)

    line = LineString(clean)
    to_metric = _transformer(STORAGE_EPSG, project.metric_crs_epsg).transform
    length = transform(to_metric, line).length
    if length < 3:
        raise StreetFieldError("The recorded road is too short; walk or drive further.")

    # Field-created codes are stable and visibly distinct from imported S###
    # codes. UUID suffix avoids a round trip/sequence race during offline replay.
    code = f"FR-{uuid.uuid4().hex[:8].upper()}"
    row = Street(
        project_id=project.id, street_code=code,
        name=name.strip() if name else None,
        name_status="named" if name else "unnamed",
        name_source="field_observed" if name else None,
        name_recorded_by=user.email if name else None,
        needs_field_name=not bool(name),
        geom=from_shape(MultiLineString([line]), srid=4326),
        length_m=round(length, 2), road_class=road_class,
        licence_class="owned", verification_state="field_observed",
        surface=surface, condition=condition, access=access, width_m=width_m,
        field_notes=field_notes, surveyed_by=user.email,
        assessed_at=datetime.now(timezone.utc), field_client_id=client_id,
    )
    db.add(row)
    db.flush()
    audit_service.record(db, actor=user, entity_type="street", entity_id=row.id,
                         action="capture_street", project_id=project.id,
                         changes={"length_m": {"before": None, "after": round(length, 1)},
                                  "name": {"before": None, "after": row.name}})
    db.commit()
    db.refresh(row)
    return _out(row)


def geojson(db: Session, project: Project, since=None) -> dict:
    q = select(Street).where(Street.project_id == project.id)
    if since is not None:
        q = q.where(Street.updated_at > since)
    features = []
    for s in db.scalars(q):
        features.append({
            "type": "Feature", "geometry": mapping(to_shape(s.geom)),
            "properties": {
                "id": str(s.id), "code": s.street_code, "name": s.name,
                "road_class": s.road_class, "surface": s.surface,
                "condition": s.condition, "access": s.access,
                "width_m": float(s.width_m) if s.width_m is not None else None,
                "surveyed_by": s.surveyed_by, "last_edited_by": s.last_edited_by,
                "verification_state": s.verification_state,
                "updated_at": s.updated_at.isoformat(), "created_at": s.created_at.isoformat(),
            },
        })
    return {"type": "FeatureCollection", "features": features}


def _out(s: Street) -> dict:
    return {
        "id": str(s.id), "code": s.street_code, "name": s.name,
        "road_class": s.road_class, "surface": s.surface,
        "condition": s.condition, "access": s.access,
        "width_m": float(s.width_m) if s.width_m is not None else None,
        "field_notes": s.field_notes, "surveyed_by": s.surveyed_by,
        "last_edited_by": s.last_edited_by,
        "verification_state": s.verification_state,
        "updated_at": s.updated_at.isoformat(),
    }
