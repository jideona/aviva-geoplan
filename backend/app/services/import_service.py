"""Import of buildings and streets, with provenance and protected writes.

Every feature that lands carries: the source it came from, that source's licence
class, its stable external identifier, and a verification state. Re-import
matches on (project, external_id) and refuses to overwrite anything a surveyor
has since confirmed (SRD FR-IMP-023, FR-IMP-024).
"""
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import LineString, MultiLineString, Polygon
from shapely.ops import transform
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.building import Building
from app.db.models.project import Project
from app.db.models.provenance import DataSource, ProvenanceRecord
from app.db.models.street import Street
from app.db.models.user import User
from app.domain.crs import _transformer, STORAGE_EPSG
from app.domain.licences import LicenceClass
from app.domain.osm import OsmParseError, parse_roads
from app.domain.overture import OvertureParseError, parse_buildings
from app.domain.streets_kml import StreetParseError, parse_streets
from app.domain.verification import is_protected
from app.services import audit_service, boundary_service

# Footprints below this are noise rather than structures. The right value is a
# judgement call to revisit once field data exists — 44% of the Wuye Overture
# load falls under 30 m2, which is either genuine secondary structures or
# detection fragments, and only survey can tell them apart.
MIN_FOOTPRINT_SQM = 3.0


class ImportError_(ValueError):
    """Message is safe to show the user."""


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped_outside_boundary: int = 0
    skipped_too_small: int = 0
    skipped_protected: int = 0
    invalid_geometry: int = 0
    licence_classes: dict[str, int] = field(default_factory=dict)
    datasets: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "skipped_outside_boundary": self.skipped_outside_boundary,
            "skipped_too_small": self.skipped_too_small,
            "skipped_protected": self.skipped_protected,
            "invalid_geometry": self.invalid_geometry,
            "licence_classes": self.licence_classes,
            "datasets": self.datasets,
            "share_alike_present": self.licence_classes.get("share_alike", 0) > 0,
        }


def _source_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _get_or_create_source(db: Session, name: str, source_type: str,
                          licence: str | None, licence_class: str) -> DataSource:
    src = db.scalar(select(DataSource).where(DataSource.name == name))
    if src is None:
        src = DataSource(name=name, source_type=source_type, licence=licence,
                         licence_class=licence_class)
        db.add(src)
        db.flush()
    return src


def _boundary_shape(db: Session, project: Project):
    boundary = boundary_service.get_current(db, project.id)
    if boundary is None:
        raise ImportError_(
            "Upload a project boundary before importing features. Without one "
            "there is nothing to clip against."
        )
    return to_shape(boundary.geom)


# --------------------------------------------------------------------------
# Buildings
# --------------------------------------------------------------------------

def import_overture_buildings(db: Session, user: User, project: Project,
                              filename: str, data: bytes) -> ImportResult:
    boundary = _boundary_shape(db, project)
    to_metric = _transformer(STORAGE_EPSG, project.metric_crs_epsg).transform

    try:
        records = list(parse_buildings(data))
    except OvertureParseError as exc:
        raise ImportError_(str(exc)) from exc

    existing = {
        b.external_id: b for b in db.scalars(
            select(Building).where(Building.project_id == project.id,
                                   Building.external_id.isnot(None))
        )
    }

    result = ImportResult()
    sources: dict[str, DataSource] = {}

    for rec in records:
        # Clip by centroid so a building straddling the boundary is counted
        # exactly once (SRD FR-IMP-011).
        centroid = rec.geometry.centroid
        if not boundary.contains(centroid):
            result.skipped_outside_boundary += 1
            continue

        metric = transform(to_metric, rec.geometry)
        area = metric.area
        if area < MIN_FOOTPRINT_SQM:
            result.skipped_too_small += 1
            continue

        geom = rec.geometry
        if not isinstance(geom, Polygon):
            # Overture buildings are polygons; anything else is unexpected.
            result.invalid_geometry += 1
            continue

        dataset_name = rec.dataset or "Overture (unattributed)"
        source_name = f"Overture Maps — {dataset_name}"
        src = sources.get(source_name)
        if src is None:
            src = _get_or_create_source(
                db, source_name, "overture", rec.licence, rec.licence_class.value)
            sources[source_name] = src

        result.datasets[dataset_name] = result.datasets.get(dataset_name, 0) + 1
        lc = rec.licence_class.value
        result.licence_classes[lc] = result.licence_classes.get(lc, 0) + 1

        found = existing.get(rec.external_id)
        if found is not None:
            if is_protected(found.verification_state):
                # A surveyor has confirmed this. An import never overrides that.
                result.skipped_protected += 1
                continue
            changed = _apply(found, rec, geom, centroid, metric, src)
            if changed:
                result.updated += 1
            else:
                result.unchanged += 1
            continue

        building = Building(project_id=project.id)
        _apply(building, rec, geom, centroid, metric, src)
        db.add(building)
        db.flush()
        db.add(ProvenanceRecord(
            entity_type="building", entity_id=building.id, data_source_id=src.id,
            external_id=rec.external_id, imported_at=func.now(),
        ))
        result.created += 1

    if result.created == 0 and result.updated == 0:
        considered = (result.skipped_outside_boundary + result.skipped_too_small
                      + result.invalid_geometry)
        raise ImportError_(
            f"Nothing was imported. {considered:,} features were read but all "
            f"were discarded: {result.skipped_outside_boundary:,} fell outside "
            f"the project boundary, {result.skipped_too_small:,} were below the "
            f"minimum footprint size. Check that this is the buildings file and "
            f"that it covers this boundary."
        )

    audit_service.record(
        db, actor=user, entity_type="building", entity_id=None,
        action="import", project_id=project.id,
        changes={"file": {"before": None, "after": filename},
                 "result": {"before": None, "after": result.as_dict()}},
    )
    db.commit()
    return result


def _apply(b: Building, rec, geom, centroid, metric, src: DataSource) -> bool:
    """Write source values onto a building. Returns True if anything changed."""
    before = (float(b.footprint_area_sqm or 0), b.external_id, b.licence_class)
    b.geom = from_shape(geom, srid=4326)
    b.centroid = from_shape(centroid, srid=4326)
    b.footprint_area_sqm = round(metric.area, 2)
    b.perimeter_m = round(metric.length, 2)
    b.name = rec.name
    b.floors_reported = rec.num_floors
    # Overture 'height' is an upstream-reported value, not a modelled raster
    # aggregate, so it belongs in the measured column.
    b.height_measured_m = rec.height_m
    b.data_source_id = src.id
    b.external_id = rec.external_id
    b.source_dataset = rec.dataset
    b.source_update_date = _source_date(rec.source_update)
    b.licence_class = rec.licence_class.value
    b.source_attributes = rec.raw or None
    if b.verification_state is None:
        b.verification_state = "imported"
    if rec.building_class in {"residential", "house", "detached", "terrace"}:
        b.use_type = "residential"
    elif rec.building_class in {"commercial", "retail", "office"}:
        b.use_type = "commercial"
    after = (float(b.footprint_area_sqm or 0), b.external_id, b.licence_class)
    return before != after


# --------------------------------------------------------------------------
# Streets
# --------------------------------------------------------------------------

def import_streets(db: Session, user: User, project: Project,
                   files: list[tuple[str, bytes]]) -> ImportResult:
    boundary = _boundary_shape(db, project)
    to_metric = _transformer(STORAGE_EPSG, project.metric_crs_epsg).transform

    src = _get_or_create_source(
        db, "Aviva Networx street survey (KML)", "manual_entry",
        "Proprietary — Aviva Networx", LicenceClass.OWNED.value)

    existing_by_name = {
        s.name.strip().lower(): s for s in db.scalars(
            select(Street).where(Street.project_id == project.id))
    }
    next_seq = db.scalar(select(func.count()).select_from(Street)
                         .where(Street.project_id == project.id)) or 0

    result = ImportResult()
    for filename, data in files:
        try:
            parsed = parse_streets(filename, data)
        except StreetParseError as exc:
            raise ImportError_(str(exc)) from exc

        by_name: dict[str, list] = {}
        for p in parsed:
            by_name.setdefault(p.name.strip(), []).append(p.geometry)

        for name, lines in by_name.items():
            geom = MultiLineString(lines)
            if not boundary.intersects(geom):
                result.skipped_outside_boundary += 1
                continue
            length = transform(to_metric, geom).length

            found = existing_by_name.get(name.lower())
            if found is not None:
                if is_protected(found.verification_state):
                    result.skipped_protected += 1
                    continue
                found.geom = from_shape(geom, srid=4326)
                found.length_m = round(length, 2)
                result.updated += 1
                continue

            next_seq += 1
            street = Street(
                project_id=project.id,
                street_code=f"{project.code_prefix}-ST-{next_seq:03d}",
                name=name,
                geom=from_shape(geom, srid=4326),
                length_m=round(length, 2),
                road_class="residential",
                data_source_id=src.id,
                external_id=filename,
                licence_class=LicenceClass.OWNED.value,
                verification_state="imported",
            )
            db.add(street)
            db.flush()
            existing_by_name[name.lower()] = street
            db.add(ProvenanceRecord(
                entity_type="street", entity_id=street.id, data_source_id=src.id,
                external_id=filename, imported_at=func.now(),
            ))
            result.created += 1
            result.datasets[filename] = 1
            result.licence_classes[LicenceClass.OWNED.value] = (
                result.licence_classes.get(LicenceClass.OWNED.value, 0) + 1)

    audit_service.record(
        db, actor=user, entity_type="street", entity_id=None, action="import",
        project_id=project.id,
        changes={"files": {"before": None, "after": [f for f, _ in files]},
                 "result": {"before": None, "after": result.as_dict()}},
    )
    db.commit()
    return result


def licence_summary(db: Session, project_id: uuid.UUID) -> dict:
    """What the project's building geometry obliges, per SAD 5.5."""
    rows = db.execute(
        select(Building.licence_class, func.count())
        .where(Building.project_id == project_id)
        .group_by(Building.licence_class)
    ).all()
    counts = {r[0]: r[1] for r in rows}
    total = sum(counts.values())
    share_alike = counts.get(LicenceClass.SHARE_ALIKE.value, 0)
    return {
        "total": total,
        "by_class": counts,
        "share_alike_count": share_alike,
        "share_alike_pct": round(share_alike / total * 100, 1) if total else 0.0,
        "blocks_commercial_delivery": share_alike > 0,
        "note": (
            "Share-alike geometry is present. A register delivered commercially "
            "from this data may itself fall under share-alike obligations."
        ) if share_alike else "No share-alike obligations on current geometry.",
    }


# --------------------------------------------------------------------------
# OSM road network
# --------------------------------------------------------------------------

def import_osm_roads(db: Session, user: User, project: Project,
                     filename: str, data: bytes) -> ImportResult:
    """Import the road network from an OSM XML export.

    Unnamed roads are imported deliberately. In Wuye the named network is
    10.9 km while the full network is 70 km; assigning buildings requires the
    geometry, and the names become a bounded field task rather than a blocker.
    """
    boundary = _boundary_shape(db, project)
    to_metric = _transformer(STORAGE_EPSG, project.metric_crs_epsg).transform

    try:
        roads = parse_roads(data)
    except OsmParseError as exc:
        raise ImportError_(str(exc)) from exc

    src = _get_or_create_source(
        db, "OpenStreetMap (Overpass)", "osm", "ODbL-1.0",
        LicenceClass.SHARE_ALIKE.value)

    existing = {
        s.external_id: s for s in db.scalars(
            select(Street).where(Street.project_id == project.id,
                                 Street.external_id.isnot(None)))
    }
    next_seq = db.scalar(select(func.count()).select_from(Street)
                         .where(Street.project_id == project.id)) or 0

    result = ImportResult()
    for road in roads:
        clipped = road.geometry.intersection(boundary)
        if clipped.is_empty:
            result.skipped_outside_boundary += 1
            continue
        parts = (list(clipped.geoms) if clipped.geom_type.startswith("Multi")
                 else [clipped])
        parts = [p for p in parts if isinstance(p, LineString) and p.length > 0]
        if not parts:
            result.invalid_geometry += 1
            continue
        geom = MultiLineString(parts)
        length = transform(to_metric, geom).length

        found = existing.get(road.external_id)
        if found is not None:
            if is_protected(found.verification_state):
                result.skipped_protected += 1
                continue
            found.geom = from_shape(geom, srid=4326)
            found.length_m = round(length, 2)
            found.road_class = road.highway
            if road.name and not found.name:
                found.name = road.name
                found.name_status = "named"
                found.needs_field_name = False
            result.updated += 1
            continue

        next_seq += 1
        street = Street(
            project_id=project.id,
            street_code=f"{project.code_prefix}-ST-{next_seq:03d}",
            name=road.name,
            name_status="named" if road.name else "unnamed",
            needs_field_name=road.name is None,
            geom=from_shape(geom, srid=4326),
            length_m=round(length, 2),
            road_class=road.highway,
            data_source_id=src.id,
            external_id=road.external_id,
            licence_class=LicenceClass.SHARE_ALIKE.value,
            verification_state="imported",
        )
        db.add(street)
        db.flush()
        existing[road.external_id] = street
        db.add(ProvenanceRecord(
            entity_type="street", entity_id=street.id, data_source_id=src.id,
            external_id=road.external_id, imported_at=func.now(),
        ))
        result.created += 1
        key = road.highway + ("" if road.name else " (unnamed)")
        result.datasets[key] = result.datasets.get(key, 0) + 1
        lc = LicenceClass.SHARE_ALIKE.value
        result.licence_classes[lc] = result.licence_classes.get(lc, 0) + 1

    audit_service.record(
        db, actor=user, entity_type="street", entity_id=None, action="import",
        project_id=project.id,
        changes={"file": {"before": None, "after": filename},
                 "result": {"before": None, "after": result.as_dict()}},
    )
    db.commit()
    return result
