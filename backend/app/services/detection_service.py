"""Ingest auto-detected building footprints and merge them into the register.

The detector (an offline tool over Esri imagery — see tools/detect_buildings.py)
produces candidate rooftop polygons. This service is the trustworthy half: it
clips candidates to the project boundary, drops ones that duplicate a building
already on file OR each other (the baseline detector splits a roof into several
blobs), and imports only the genuinely new ones — tagged exactly like a
hand-trace over the same imagery (desk_reference_restricted, pilot-only), so the
licence position is unchanged. Detected footprints are rooftops, not premises.

`dry_run=True` runs the whole pipeline but writes nothing — it returns what WOULD
import plus a preview FeatureCollection, so a noisy detection can be inspected on
the map before anything touches the register.
"""
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import mapping, shape
from shapely.ops import transform
from shapely.strtree import STRtree
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models.building import Building
from app.db.models.project import Project
from app.db.models.provenance import DataSource, ProvenanceRecord
from app.db.models.user import User
from app.domain.building_edit import rules_for
from app.domain.crs import STORAGE_EPSG, _transformer
from app.services import audit_service, boundary_service

MIN_SQM = 3.0
MAX_SQM = 100_000.0
DEFAULT_OVERLAP = 0.30          # counts as a duplicate above this area fraction
_SOURCE_NAME = "Esri auto-detection (pilot)"


class DetectionError(ValueError):
    """Message is safe to show the user."""


def ingest_candidates(db: Session, user: User, project: Project,
                      geojson: dict, overlap_threshold: float = DEFAULT_OVERLAP,
                      capture_source: str = "traced_reference",
                      dry_run: bool = False) -> dict:
    feats = (geojson or {}).get("features")
    if not isinstance(feats, list) or not feats:
        raise DetectionError("No candidate features found in the upload.")
    try:
        rules = rules_for(capture_source)
    except (KeyError, ValueError) as exc:
        raise DetectionError(f"Unknown capture source {capture_source!r}.") from exc

    to_metric = _transformer(STORAGE_EPSG, project.metric_crs_epsg).transform
    boundary = boundary_service.get_current(db, project.id)
    boundary_geom = to_shape(boundary.geom) if boundary is not None else None

    existing = [to_shape(b.geom) for b in db.scalars(select(Building).where(
        Building.project_id == project.id, Building.excluded.is_(False)))]
    existing_tree = STRtree(existing) if existing else None

    # First pass: clip to boundary, size-filter, and drop candidates that
    # duplicate an existing building.
    survivors: list = []                 # (poly, area_m, perim_m, conf)
    duplicates = out_of_bounds = invalid = 0
    for f in feats:
        geom = f.get("geometry") if isinstance(f, dict) else None
        try:
            poly = shape(geom)
        except (AttributeError, TypeError, ValueError):
            invalid += 1
            continue
        if poly.geom_type != "Polygon" or poly.is_empty:
            invalid += 1
            continue
        if not poly.is_valid:
            poly = poly.buffer(0)
            if poly.geom_type != "Polygon" or poly.is_empty:
                invalid += 1
                continue
        if boundary_geom is not None and not boundary_geom.contains(poly.centroid):
            out_of_bounds += 1
            continue
        metric = transform(to_metric, poly)
        area = metric.area
        if area < MIN_SQM or area > MAX_SQM:
            invalid += 1
            continue
        if existing_tree is not None and _overlaps(poly, existing_tree,
                                                   existing, overlap_threshold):
            duplicates += 1
            continue
        conf = _confidence(f)
        survivors.append((poly, area, metric.length, conf))

    # Second pass: dedupe survivors against EACH OTHER (a roof split into blobs).
    merged, kept = _dedupe_within(survivors, overlap_threshold)

    summary = {
        "candidates": len(feats),
        "duplicates_skipped": duplicates,
        "merged_overlaps": merged,
        "outside_boundary": out_of_bounds,
        "invalid": invalid,
        "would_import": len(kept),
        "licence_class": rules["licence_class"],
        "commercial_ready": rules["commercial_ready"],
        "dry_run": dry_run,
        "note": ("Rooftops, not premises; pilot-only (derived from display-only "
                 "Esri imagery). Re-source over owned imagery or field-confirm "
                 "before commercial use."),
    }

    if dry_run:
        summary["imported"] = 0
        summary["preview"] = {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "geometry": mapping(p),
                          "properties": {"area": round(a, 1),
                                         "kind": "detect_preview"}}
                         for (p, a, _per, _c) in kept]}
        return summary

    # Persist.
    src = db.scalar(select(DataSource).where(DataSource.name == _SOURCE_NAME))
    if src is None:
        src = DataSource(name=_SOURCE_NAME, source_type="ml_detection",
                         licence_class=rules["licence_class"],
                         admitted_role="Auto-detected over display-only imagery.")
        db.add(src)
        db.flush()
    for poly, area, perim, conf in kept:
        b = Building(
            project_id=project.id,
            geom=from_shape(poly, srid=4326),
            centroid=from_shape(poly.centroid, srid=4326),
            footprint_area_sqm=round(area, 2), perimeter_m=round(perim, 2),
            building_type="unclassified", use_type="unknown",
            data_source_id=src.id, source_dataset="Esri auto-detection",
            licence_class=rules["licence_class"],
            verification_state=rules["verification_state"],
            detection_confidence=conf)
        db.add(b)
        db.flush()
        db.add(ProvenanceRecord(entity_type="building", entity_id=b.id,
                                data_source_id=src.id,
                                notes="Auto-detected (Esri, pilot-only)."))
    audit_service.record(
        db, actor=user, entity_type="project", entity_id=project.id,
        action="detect_import", project_id=project.id,
        changes={"imported": {"before": None, "after": len(kept)},
                 "duplicates": {"before": None, "after": duplicates}})
    db.commit()
    summary["imported"] = len(kept)
    return summary


def clear_detected(db: Session, user: User, project: Project) -> dict:
    """Delete every building imported from the Esri auto-detection source — the
    undo for a test import. Auto-detections are regenerable, so this is a hard
    delete (surveyed/imported buildings are never touched)."""
    src = db.scalar(select(DataSource).where(DataSource.name == _SOURCE_NAME))
    if src is None:
        return {"deleted": 0}
    ids = [b.id for b in db.scalars(select(Building).where(
        Building.project_id == project.id, Building.data_source_id == src.id))]
    if not ids:
        return {"deleted": 0}
    db.execute(delete(ProvenanceRecord).where(
        ProvenanceRecord.entity_type == "building",
        ProvenanceRecord.entity_id.in_(ids)))
    db.execute(delete(Building).where(Building.id.in_(ids)))
    audit_service.record(
        db, actor=user, entity_type="project", entity_id=project.id,
        action="clear_detected", project_id=project.id,
        changes={"deleted": {"before": len(ids), "after": 0}})
    db.commit()
    return {"deleted": len(ids)}


def _confidence(feature) -> float | None:
    props = feature.get("properties") if isinstance(feature, dict) else None
    if isinstance(props, dict):
        c = props.get("confidence")
        if isinstance(c, (int, float)):
            return round(float(c), 4)
    return None


def _overlaps(poly, tree: STRtree, geoms: list, threshold: float) -> bool:
    for idx in tree.query(poly):
        other = geoms[int(idx)]
        inter = poly.intersection(other)
        if not inter.is_empty and inter.area / poly.area >= threshold:
            return True
    return False


def _dedupe_within(survivors: list, threshold: float):
    """Drop later survivors that overlap an earlier kept one (split roofs).
    Returns (merged_count, kept_list)."""
    if not survivors:
        return 0, []
    polys = [s[0] for s in survivors]
    tree = STRtree(polys)
    keep = [True] * len(survivors)
    for i, poly in enumerate(polys):
        if not keep[i]:
            continue
        for j in tree.query(poly):
            j = int(j)
            if j <= i or not keep[j]:
                continue
            inter = poly.intersection(polys[j])
            if inter.is_empty:
                continue
            smaller = min(poly.area, polys[j].area)
            if smaller > 0 and inter.area / smaller >= threshold:
                keep[j] = False
    kept = [survivors[i] for i in range(len(survivors)) if keep[i]]
    return keep.count(False), kept
