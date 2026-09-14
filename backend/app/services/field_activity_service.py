"""Field activity feed — a manager-facing, reverse-chronological view of what
has actually arrived from the field.

Every field capture and edit already writes an append-only AuditLog row
(building_edit_service, manhole_service, building_photo_service,
survey_route_service, media_service all call audit_service.record). This
module reads that trail back out, filtered to the entity types a field
surveyor actually produces, so an office manager can:

  - confirm a specific capture reached the server at all (images, coordinates,
    building edits — not just "the app said it synced"),
  - see who captured or changed what, and when (SRD FR-AUD-001..003 already
    requires the trail to exist; this is the first thing that reads it back),
  - reconcile/differentiate: tell a brand-new record from one that already
    existed and was just modified in the field.

Nothing here is a second source of truth — it is a read model over AuditLog,
so it can never drift from what the audit trail already asserts.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime

from geoalchemy2.shape import to_shape
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.audit import AuditLog
from app.db.models.building import Building
from app.db.models.building_photo import BuildingPhoto
from app.db.models.manhole import Manhole
from app.db.models.media import MediaAsset
from app.db.models.project import Project
from app.db.models.survey_route import SurveyRoute

# What a field surveyor's app actually produces, plus building edits made from
# either the office or a field device. Deliberately excludes bulk import /
# desk-only entity types (street naming review, design runs, etc.) so the feed
# reads as "field activity", not "everything that ever touched the database".
FIELD_ENTITY_TYPES = ("building", "manhole", "building_photo", "survey_route",
                      "media_asset")

# First sighting of an entity in the WHOLE audit trail (not just this page) is
# reported as "captured"; anything after is "modified" — this is the
# reconcile/differentiate distinction the office asked for, without a second
# "is_new" column that could drift out of sync with the trail itself.
#
# media_asset is keyed by lat/lon columns, not a PostGIS geometry, so it is
# handled separately from the generic loaders below rather than forced into
# the same shape.
_GEOM_LOADERS = {
    "building": (Building, "centroid"),
    "manhole": (Manhole, "geom"),
    "building_photo": (BuildingPhoto, "geom"),
    "survey_route": (SurveyRoute, "geom"),
}


@dataclass
class ActivityItem:
    id: str
    occurred_at: str
    surveyor: str | None
    entity_type: str
    entity_id: str | None
    action: str
    change_kind: str            # "captured" | "modified"
    changes: dict | None
    lon: float | None
    lat: float | None


def _first_point(shape) -> tuple[float, float]:
    # Buildings are polygons (centroid); manholes/photos/route points are
    # points; a route is a line — use its first vertex so it still lands
    # somewhere sensible on the map.
    if shape.geom_type == "Point":
        return shape.x, shape.y
    if shape.geom_type in ("LineString", "MultiLineString"):
        pt = list(shape.coords)[0] if shape.geom_type == "LineString" \
            else list(shape.geoms[0].coords)[0]
        return pt[0], pt[1]
    c = shape.centroid
    return c.x, c.y


def feed(db: Session, project: Project, *, surveyor: str | None = None,
         entity_type: str | None = None, since: datetime | None = None,
         until: datetime | None = None, limit: int = 100, offset: int = 0) -> dict:
    entity_types = (entity_type,) if entity_type else FIELD_ENTITY_TYPES

    base = select(AuditLog).where(
        AuditLog.project_id == project.id,
        AuditLog.entity_type.in_(entity_types))
    if surveyor:
        base = base.where(AuditLog.actor_email == surveyor)
    if since is not None:
        base = base.where(AuditLog.occurred_at >= since)
    if until is not None:
        base = base.where(AuditLog.occurred_at <= until)

    total = db.scalar(select(func.count()).select_from(base.subquery()))

    rows = list(db.scalars(
        base.order_by(AuditLog.occurred_at.desc()).limit(limit).offset(offset)))

    # First-seen action per (entity_type, entity_id) across the WHOLE trail
    # (not just this page) decides "captured" vs "modified" — a record edited
    # for the fifth time today must not read as "captured" just because its
    # first capture fell off an earlier page.
    keys = {(r.entity_type, r.entity_id) for r in rows if r.entity_id is not None}
    # Keyed by the earliest row's own id (not its action name) — two edits of
    # the same kind (e.g. a building field_update'd twice) must not both read
    # as "captured" just because they share an action string.
    first_id: dict[tuple[str, uuid.UUID], uuid.UUID] = {}
    for etype, eid in keys:
        earliest = db.scalar(
            select(AuditLog.id).where(
                AuditLog.entity_type == etype, AuditLog.entity_id == eid)
            .order_by(AuditLog.occurred_at.asc()).limit(1))
        if earliest is not None:
            first_id[(etype, eid)] = earliest

    # Batch-load current geometry for whatever entities appear on this page,
    # grouped by type, one query per type rather than one per row.
    geoms: dict[tuple[str, uuid.UUID], tuple[float, float]] = {}
    by_type: dict[str, list[uuid.UUID]] = {}
    media_ids: list[uuid.UUID] = []
    for r in rows:
        if r.entity_id is None:
            continue
        if r.entity_type == "media_asset":
            media_ids.append(r.entity_id)
        elif r.entity_type in _GEOM_LOADERS:
            by_type.setdefault(r.entity_type, []).append(r.entity_id)
    for etype, ids in by_type.items():
        model, geom_attr = _GEOM_LOADERS[etype]
        for obj in db.scalars(select(model).where(model.id.in_(ids))):
            try:
                geoms[(etype, obj.id)] = _first_point(to_shape(getattr(obj, geom_attr)))
            except Exception:  # noqa: BLE001 — a bad/missing geometry must not sink the feed
                continue
    if media_ids:
        # A photo/video is where it was captured, not where its parent entity
        # is — lat/lon are plain columns here, no PostGIS shape to parse.
        for m in db.scalars(select(MediaAsset).where(MediaAsset.id.in_(media_ids))):
            if m.captured_lat is not None and m.captured_lon is not None:
                geoms[("media_asset", m.id)] = (float(m.captured_lon), float(m.captured_lat))

    items = []
    for r in rows:
        key = (r.entity_type, r.entity_id) if r.entity_id else None
        is_create = key is not None and first_id.get(key) == r.id
        lon, lat = geoms.get(key, (None, None)) if key else (None, None)
        items.append(ActivityItem(
            id=str(r.id), occurred_at=r.occurred_at.isoformat(),
            surveyor=r.actor_email, entity_type=r.entity_type,
            entity_id=str(r.entity_id) if r.entity_id else None,
            action=r.action, change_kind="captured" if is_create else "modified",
            changes=r.changes, lon=lon, lat=lat))

    return {"items": [i.__dict__ for i in items], "total": total,
            "limit": limit, "offset": offset}


def surveyors(db: Session, project: Project) -> list[str]:
    """Distinct surveyors who have contributed field activity, for a filter
    dropdown — office users who never touch the app should not appear."""
    rows = db.scalars(
        select(AuditLog.actor_email).where(
            AuditLog.project_id == project.id,
            AuditLog.entity_type.in_(FIELD_ENTITY_TYPES),
            AuditLog.actor_email.isnot(None)).distinct())
    return sorted({r for r in rows})
