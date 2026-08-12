"""Street naming with source attribution (SRD FR-STA-009)."""
import uuid

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import MultiLineString
from shapely.ops import linemerge, transform, unary_union
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db.models.building import Building
from app.db.models.project import Project
from app.db.models.street import Street
from app.domain.crs import STORAGE_EPSG, _transformer
from app.domain.name_matching import merge_key
from app.db.models.user import User
from app.domain.licences import LicenceClass, clearance_note
from app.domain.naming import NameSource, re_source_required, rules_for
from app.domain.verification import is_protected, rank
from app.services import audit_service


class NamingError(ValueError):
    """Message is safe to show the user."""


def name_street(db: Session, user: User, project: Project, street_id: uuid.UUID,
                name: str, source: str, note: str | None = None,
                evidence_key: str | None = None) -> Street:
    street = db.scalar(select(Street).where(Street.id == street_id,
                                            Street.project_id == project.id))
    if street is None:
        raise NamingError("Street not found.")

    name = name.strip()
    if len(name) < 2:
        raise NamingError("A street name must be at least two characters.")

    try:
        rules = rules_for(source)
    except (KeyError, ValueError) as exc:
        raise NamingError(
            f"Unknown name source {source!r}. Valid: "
            f"{', '.join(s.value for s in NameSource)}"
        ) from exc

    # A weaker source never displaces a stronger one (FR-STA-005).
    if (street.name and street.name_source
            and rank(street.verification_state) > rank(rules.verification)):
        raise NamingError(
            f"{street.street_code} is already named from a stronger source "
            f"({street.name_source}). Downgrading requires a QA reviewer."
        )
    if is_protected(street.verification_state) and rules.verification.value == "desk_verified":
        raise NamingError(
            f"{street.street_code} has been field verified. A desk source "
            "cannot overwrite it."
        )

    before = {"name": street.name, "name_source": street.name_source,
              "licence_class": street.licence_class,
              "verification_state": street.verification_state}

    street.name = name
    street.name_source = source
    street.name_status = "named"
    street.needs_field_name = not rules.commercial_ready
    street.name_recorded_by = user.email
    street.name_note = note
    street.name_evidence_key = evidence_key
    street.verification_state = rules.verification.value
    # The street geometry keeps its own licence; the name carries the stricter
    # of the two, because the record as delivered contains both.
    if rules.licence_class is not LicenceClass.OWNED:
        street.licence_class = rules.licence_class.value

    audit_service.record(
        db, actor=user, entity_type="street", entity_id=street.id,
        action="name", project_id=project.id,
        changes=audit_service.diff(before, {
            "name": street.name, "name_source": street.name_source,
            "licence_class": street.licence_class,
            "verification_state": street.verification_state}),
    )

    # A street is a named thing, not a topological segment. OSM splits ways at
    # junctions and surface changes, so one road arrives as many rows; giving
    # two of them the same name means they are the same street.
    street = _absorb_same_named(db, user, project, street)

    db.commit()
    db.refresh(street)
    return street


def _absorb_same_named(db: Session, user: User, project: Project,
                       street: Street) -> Street:
    """Merge every other segment carrying this name into one street record."""
    key = merge_key(street.name or "")
    if not key:
        return street

    siblings = [
        s for s in db.scalars(
            select(Street).where(Street.project_id == project.id,
                                 Street.id != street.id,
                                 Street.name.isnot(None)))
        if merge_key(s.name or "") == key
    ]
    if not siblings:
        return street

    # Keep the earliest-coded record so the identifier stays stable.
    group = sorted([street, *siblings], key=lambda s: s.street_code)
    keeper, absorbed = group[0], group[1:]

    parts = []
    for s in group:
        geom = to_shape(s.geom)
        parts.extend(geom.geoms if geom.geom_type == "MultiLineString" else [geom])
    merged = linemerge(unary_union(parts))
    if merged.geom_type == "LineString":
        merged = MultiLineString([merged])

    to_metric = _transformer(STORAGE_EPSG, project.metric_crs_epsg).transform
    keeper.geom = from_shape(merged, srid=4326)
    keeper.length_m = round(transform(to_metric, merged).length, 2)
    keeper.name = street.name
    keeper.name_source = street.name_source
    keeper.name_status = street.name_status
    keeper.needs_field_name = street.needs_field_name
    keeper.verification_state = street.verification_state
    keeper.name_recorded_by = street.name_recorded_by

    for s in absorbed:
        db.execute(update(Building)
                   .where(Building.street_id == s.id)
                   .values(street_id=keeper.id))
        db.delete(s)

    audit_service.record(
        db, actor=user, entity_type="street", entity_id=keeper.id,
        action="merge_segments", project_id=project.id,
        changes={"absorbed": {"before": None,
                              "after": [s.street_code for s in absorbed]},
                 "length_m": {"before": None, "after": float(keeper.length_m)}},
    )
    db.flush()
    return keeper


def bulk_name(db: Session, user: User, project: Project,
              entries: list[dict]) -> dict:
    named, failed = 0, []
    for entry in entries:
        try:
            name_street(db, user, project, uuid.UUID(str(entry["street_id"])),
                        entry["name"], entry["source"], entry.get("note"))
            named += 1
        except (NamingError, KeyError, ValueError) as exc:
            failed.append({"street_id": str(entry.get("street_id")),
                           "error": str(exc)})
    return {"named": named, "failed": failed}


def clearance(db: Session, project_id: uuid.UUID) -> dict:
    """Whether the project's data could be delivered commercially today."""
    b_classes = {r[0] for r in db.execute(
        select(Building.licence_class).where(Building.project_id == project_id)
        .group_by(Building.licence_class)).all()}
    s_classes = {r[0] for r in db.execute(
        select(Street.licence_class).where(Street.project_id == project_id)
        .group_by(Street.licence_class)).all()}
    sources = [r[0] for r in db.execute(
        select(Street.name_source).where(Street.project_id == project_id,
                                         Street.name_source.isnot(None))
        .group_by(Street.name_source)).all()]

    classes = set()
    for c in b_classes | s_classes:
        try:
            classes.add(LicenceClass(c))
        except ValueError:
            continue

    blocked = re_source_required(sources)
    counts = dict(db.execute(
        select(Street.name_source, func.count())
        .where(Street.project_id == project_id, Street.name_source.isnot(None))
        .group_by(Street.name_source)).all())
    re_source_count = sum(counts.get(s, 0) for s in blocked)

    return {
        "clear_for_commercial_delivery": not blocked and not (
            LicenceClass.SHARE_ALIKE in classes),
        "note": clearance_note(classes),
        "name_sources": counts,
        "sources_requiring_re_sourcing": blocked,
        "streets_requiring_re_sourcing": re_source_count,
        "remedy": (
            f"{re_source_count} street names must be re-sourced from a field or "
            "authority source before this register is delivered or sold. They "
            "are tagged, so the work is bounded."
        ) if re_source_count else "No street names require re-sourcing.",
    }


def consolidate(db: Session, user: User, project: Project) -> dict:
    """Merge segments that already share a name.

    Needed once, for names entered before naming merged automatically.
    """
    streets = list(db.scalars(select(Street).where(
        Street.project_id == project.id, Street.name.isnot(None))))
    groups: dict[str, list[Street]] = {}
    for s in streets:
        groups.setdefault(merge_key(s.name or ""), []).append(s)

    merged, removed = 0, 0
    for key, group in groups.items():
        if not key or len(group) < 2:
            continue
        keeper = sorted(group, key=lambda s: s.street_code)[0]
        before = len(group)
        _absorb_same_named(db, user, project, keeper)
        merged += 1
        removed += before - 1

    db.commit()
    remaining = db.scalar(select(func.count()).select_from(Street)
                          .where(Street.project_id == project.id)) or 0
    named = db.scalar(select(func.count()).select_from(Street)
                      .where(Street.project_id == project.id,
                             Street.name.isnot(None))) or 0
    return {
        "streets_merged": merged,
        "segments_absorbed": removed,
        "streets_remaining": remaining,
        "named_streets": named,
        "note": (f"{removed} duplicate segments folded into {merged} streets. "
                 "Naming now merges automatically, so this is a one-off.")
        if removed else "No duplicate names found.",
    }
