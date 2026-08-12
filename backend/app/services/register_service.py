"""Building register queries and summary (SRD FR-PRM-012)."""
import uuid
from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.models.building import Building
from app.db.models.street import Street

SORTABLE = {
    "area": Building.footprint_area_sqm,
    "code": Building.building_code,
    "confidence": Building.street_assignment_confidence,
    "type": Building.building_type,
    "verification": Building.verification_state,
}


@dataclass
class RegisterFilter:
    street_id: uuid.UUID | None = None
    verification_state: str | None = None
    building_type: str | None = None
    use_type: str | None = None
    licence_class: str | None = None
    unassigned_only: bool = False
    needs_review: bool = False
    min_area: float | None = None
    max_area: float | None = None
    search: str | None = None

    def describe(self) -> str:
        """Human-readable filter description, recorded on every export."""
        parts = []
        if self.street_id: parts.append(f"street={self.street_id}")
        if self.verification_state: parts.append(f"verification={self.verification_state}")
        if self.building_type: parts.append(f"type={self.building_type}")
        if self.use_type: parts.append(f"use={self.use_type}")
        if self.licence_class: parts.append(f"licence={self.licence_class}")
        if self.unassigned_only: parts.append("unassigned only")
        if self.needs_review: parts.append("assignment confidence below 0.7")
        if self.min_area is not None: parts.append(f"area >= {self.min_area} m2")
        if self.max_area is not None: parts.append(f"area <= {self.max_area} m2")
        if self.search: parts.append(f"search='{self.search}'")
        return "; ".join(parts) if parts else "no filter — full register"


def apply_filter(stmt: Select, project_id: uuid.UUID, f: RegisterFilter) -> Select:
    stmt = stmt.where(Building.project_id == project_id,
                      Building.excluded.is_(False))
    if f.street_id:
        stmt = stmt.where(Building.street_id == f.street_id)
    if f.verification_state:
        stmt = stmt.where(Building.verification_state == f.verification_state)
    if f.building_type:
        stmt = stmt.where(Building.building_type == f.building_type)
    if f.use_type:
        stmt = stmt.where(Building.use_type == f.use_type)
    if f.licence_class:
        stmt = stmt.where(Building.licence_class == f.licence_class)
    if f.unassigned_only:
        stmt = stmt.where(Building.street_id.is_(None))
    if f.needs_review:
        stmt = stmt.where((Building.street_assignment_confidence < 0.7) |
                          (Building.street_assignment_confidence.is_(None)))
    if f.min_area is not None:
        stmt = stmt.where(Building.footprint_area_sqm >= f.min_area)
    if f.max_area is not None:
        stmt = stmt.where(Building.footprint_area_sqm <= f.max_area)
    if f.search:
        like = f"%{f.search.strip()}%"
        stmt = stmt.where((Building.building_code.ilike(like)) |
                          (Building.name.ilike(like)) |
                          (Street.name.ilike(like)))
    return stmt


def query(db: Session, project_id: uuid.UUID, f: RegisterFilter,
          sort: str = "area", descending: bool = True,
          limit: int | None = 100, offset: int = 0):
    stmt = (select(Building, Street.name, Street.street_code)
            .outerjoin(Street, Building.street_id == Street.id))
    stmt = apply_filter(stmt, project_id, f)
    col = SORTABLE.get(sort, Building.footprint_area_sqm)
    stmt = stmt.order_by(col.desc().nullslast() if descending
                         else col.asc().nullsfirst())
    if limit is not None:
        stmt = stmt.limit(limit).offset(offset)
    return db.execute(stmt).all()


def count(db: Session, project_id: uuid.UUID, f: RegisterFilter) -> int:
    stmt = (select(func.count(Building.id))
            .select_from(Building)
            .outerjoin(Street, Building.street_id == Street.id))
    return db.scalar(apply_filter(stmt, project_id, f)) or 0


def summary(db: Session, project_id: uuid.UUID) -> dict:
    total = db.scalar(select(func.count()).select_from(Building)
                      .where(Building.project_id == project_id)) or 0
    assigned = db.scalar(select(func.count()).select_from(Building)
                         .where(Building.project_id == project_id,
                                Building.street_id.isnot(None))) or 0
    area = db.scalar(select(func.coalesce(func.sum(Building.footprint_area_sqm), 0))
                     .where(Building.project_id == project_id)) or 0
    median = db.scalar(
        select(func.percentile_cont(0.5).within_group(
            Building.footprint_area_sqm.asc()))
        .where(Building.project_id == project_id))
    surveyed = db.scalar(select(func.count()).select_from(Building)
                         .where(Building.project_id == project_id,
                                Building.units_surveyed.isnot(None))) or 0
    est = db.scalar(select(func.coalesce(func.sum(Building.premises_estimated), 0))
                    .where(Building.project_id == project_id)) or 0
    streets = db.scalar(select(func.count()).select_from(Street)
                        .where(Street.project_id == project_id)) or 0
    named = db.scalar(select(func.count()).select_from(Street)
                      .where(Street.project_id == project_id,
                             Street.name.isnot(None))) or 0

    by_state = dict(db.execute(
        select(Building.verification_state, func.count())
        .where(Building.project_id == project_id)
        .group_by(Building.verification_state)).all())
    by_licence = dict(db.execute(
        select(Building.licence_class, func.count())
        .where(Building.project_id == project_id)
        .group_by(Building.licence_class)).all())

    return {
        "buildings": total,
        "assigned_to_street": assigned,
        "unassigned": total - assigned,
        "assigned_pct": round(assigned / total * 100, 1) if total else 0.0,
        "streets": streets,
        "streets_named": named,
        "streets_unnamed": streets - named,
        "total_footprint_sqm": round(float(area), 1),
        "median_footprint_sqm": round(float(median), 1) if median else None,
        "buildings_surveyed": surveyed,
        "premises_estimated_total": int(est),
        # Premises figures are only meaningful once the estimation model has
        # been calibrated against survey returns (SRD FR-PRM-008).
        "premises_basis": ("survey-calibrated" if surveyed
                           else "not yet calibrated — no survey data"),
        "by_verification_state": by_state,
        "by_licence_class": by_licence,
    }
