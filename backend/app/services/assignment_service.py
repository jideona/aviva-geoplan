"""Street assignment orchestration (SRD FR-STA-001 to FR-STA-008)."""
import uuid

from geoalchemy2.shape import to_shape
from shapely.ops import transform
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.building import Building
from app.db.models.project import Project
from app.db.models.street import Street
from app.db.models.user import User
from app.domain.crs import STORAGE_EPSG, _transformer
from app.domain.osm import CLASS_RANK, DEFAULT_RANK
from app.domain.street_assignment import (AssignmentCandidate, AssignmentParams,
                                          assign, summarise)
from app.domain.verification import is_protected
from app.services import audit_service


def run_assignment(db: Session, user: User, project: Project,
                   params: AssignmentParams | None = None,
                   only_unassigned: bool = True) -> dict:
    params = params or AssignmentParams()
    to_metric = _transformer(STORAGE_EPSG, project.metric_crs_epsg).transform

    streets = list(db.scalars(select(Street).where(Street.project_id == project.id)))
    if not streets:
        return {"total": 0, "assigned": 0, "unassigned": 0, "high_confidence": 0,
                "needs_review": 0, "low_confidence": 0, "needs_field_name": 0,
                "note": "No streets imported yet."}

    candidates = [
        AssignmentCandidate(
            street_id=str(s.id),
            name=s.name,
            class_rank=CLASS_RANK.get(s.road_class, DEFAULT_RANK),
            geometry=transform(to_metric, to_shape(s.geom)),
        )
        for s in streets
    ]

    stmt = select(Building).where(Building.project_id == project.id)
    if only_unassigned:
        stmt = stmt.where(Building.street_id.is_(None))
    buildings = list(db.scalars(stmt))

    protected = 0
    payload = []
    lookup: dict[str, Building] = {}
    for b in buildings:
        if is_protected(b.verification_state):
            # A surveyor has confirmed this address. The algorithm does not
            # override it (FR-STA-005).
            protected += 1
            continue
        # Access point preference: gate, then entrance, then centroid.
        # Gate and entrance arrive with the survey phase; centroid until then.
        point = transform(to_metric, to_shape(b.centroid))
        payload.append((str(b.id), point))
        lookup[str(b.id)] = b

    proposals = assign(payload, candidates, params)

    for p in proposals:
        b = lookup[p.building_id]
        b.street_id = uuid.UUID(p.street_id) if p.street_id else None
        b.street_assignment_confidence = p.confidence
        b.street_assignment_reason = p.reason
        b.street_assignment_distance_m = (None if p.distance_m == float("inf")
                                          else p.distance_m)

    result = summarise(proposals)
    result["skipped_protected"] = protected
    result["max_distance_m"] = params.max_distance_m

    audit_service.record(
        db, actor=user, entity_type="building", entity_id=None,
        action="street_assignment", project_id=project.id,
        changes={"params": {"before": None,
                            "after": {"max_distance_m": params.max_distance_m}},
                 "result": {"before": None, "after": result}},
    )
    db.commit()
    return result


def review_queue(db: Session, project_id: uuid.UUID, limit: int = 200,
                 max_confidence: float = 0.7) -> list[Building]:
    """Low-confidence and unassigned buildings, worst first (FR-STA-007)."""
    return list(db.scalars(
        select(Building)
        .where(Building.project_id == project_id)
        .where((Building.street_id.is_(None)) |
               (Building.street_assignment_confidence < max_confidence))
        .order_by(Building.street_assignment_confidence.asc().nullsfirst(),
                  Building.footprint_area_sqm.desc())
        .limit(limit)
    ))


def reassign(db: Session, user: User, project: Project, building_id: uuid.UUID,
             street_id: uuid.UUID | None) -> Building:
    """Manual override. Records the change and marks it desk verified."""
    b = db.scalar(select(Building).where(Building.id == building_id,
                                         Building.project_id == project.id))
    if b is None:
        raise ValueError("Building not found.")

    before = {"street_id": b.street_id, "verification_state": b.verification_state}
    b.street_id = street_id
    b.street_assignment_confidence = 1.0
    b.street_assignment_reason = "manually assigned"
    if not is_protected(b.verification_state):
        b.verification_state = "desk_verified"

    audit_service.record(
        db, actor=user, entity_type="building", entity_id=b.id,
        action="reassign_street", project_id=project.id,
        changes=audit_service.diff(before, {"street_id": b.street_id,
                                            "verification_state": b.verification_state}),
    )
    db.commit()
    db.refresh(b)
    return b


def naming_queue(db: Session, project_id: uuid.UUID) -> list[dict]:
    """Unnamed roads ranked by how many buildings depend on them.

    This is the field work list: naming these converts a geometric assignment
    into a usable address.
    """
    rows = db.execute(
        select(Street, func.count(Building.id))
        .outerjoin(Building, Building.street_id == Street.id)
        .where(Street.project_id == project_id, Street.needs_field_name.is_(True))
        .group_by(Street.id)
        .order_by(func.count(Building.id).desc())
    ).all()
    return [{"id": str(s.id), "street_code": s.street_code,
             "name": s.name, "name_source": s.name_source,
             "road_class": s.road_class, "length_m": float(s.length_m),
             "building_count": n} for s, n in rows]
