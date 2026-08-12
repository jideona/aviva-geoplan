"""Fetch-once, cache-forever lookup for reference boundary data.

On a cache miss this reaches two public sources:
  - GRID3's ward FeatureServer (Esri REST), for kind="ward"
  - OSM's Overpass API, admin_level=7 district relations, for kind="district"

Every successful fetch is written to `reference_boundary`, keyed on
(source, source_ref), so a repeat lookup for the same name never touches the
network again — see app/db/models/reference_boundary.py for why that matters
(GRID3's previous GeoServer endpoint went NXDOMAIN with no notice, silently
breaking anything that depended on it live). A miss or an upstream failure
returns None rather than raising: an unmatched district name, or the fetch
being temporarily unavailable, is a normal outcome that callers (project
creation) should shrug off and continue without a boundary, not a hard error.
"""
import logging
from datetime import datetime, timezone

import httpx
from geoalchemy2.shape import from_shape
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry import shape as shapely_shape
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models.reference_boundary import ReferenceBoundary
from app.domain.boundary import BoundaryParseError, validate_boundary
from app.domain.crs import DEFAULT_METRIC_EPSG, area_sqm
from app.domain.reference_sources import (RingAssemblyError, assemble_rings,
                                          normalize_name)

logger = logging.getLogger(__name__)

GRID3_WARD_QUERY_URL = (
    "https://services3.arcgis.com/BU6Aadhn6tbBEdyk/arcgis/rest/services/"
    "NGA_Ward_Boundaries/FeatureServer/0/query"
)
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# GRID3's own state code, keyed by the "NG-<region>" convention already used
# in app/domain/crs.py. Only FCT is in scope for now (Abuja pilot); adding a
# state here is what "expanding scope" looks like later.
_STATE_TO_GRID3_CODE = {"NG-FCT": "FC"}


class ReferenceFetchError(Exception):
    """An upstream fetch or geometry problem. Always caught internally by
    `ensure_boundary_for_district` — kept as a distinct type so callers that
    invoke the private fetchers directly (e.g. tests) can assert on it.
    """


def find_cached(db: Session, name: str, kind: str | None = None) -> ReferenceBoundary | None:
    """Cache lookup only — never touches the network."""
    q = select(ReferenceBoundary).where(
        ReferenceBoundary.name_normalized == normalize_name(name))
    if kind:
        q = q.where(ReferenceBoundary.kind == kind)
    return db.scalar(q.order_by(ReferenceBoundary.fetched_at.desc()))


def ensure_boundary_for_district(
    db: Session, district_name: str, state_code: str = "NG-FCT",
) -> ReferenceBoundary | None:
    """Cache-first lookup: returns the cached row if we already have this
    district or ward, otherwise tries GRID3 (ward, more precise and
    government-adjacent) then falls back to OSM (district relation).
    Never raises — logs and returns None on any upstream problem, since
    project creation should still succeed without an auto-attached boundary.
    """
    cached = find_cached(db, district_name)
    if cached is not None:
        return cached

    settings = get_settings()
    if not settings.auto_fetch_reference_boundaries:
        return None

    try:
        row = _fetch_grid3_ward(db, district_name, state_code)
        if row is None:
            row = _fetch_osm_district(db, district_name, state_code)
    except ReferenceFetchError as exc:
        logger.warning(
            "Reference boundary auto-fetch failed for %r: %s", district_name, exc)
        return None

    if row is None:
        logger.info(
            "No GRID3 ward or OSM district match for %r; project created "
            "without an auto-attached boundary.", district_name)
    return row


def _fetch_grid3_ward(
    db: Session, name: str, state_code: str,
) -> ReferenceBoundary | None:
    grid3_state = _STATE_TO_GRID3_CODE.get(state_code)
    if grid3_state is None:
        return None

    params = {
        "where": f"statecode='{grid3_state}'",
        "outFields": "*",
        "geometryPrecision": 6,
        "f": "geojson",
    }
    try:
        resp = httpx.get(
            GRID3_WARD_QUERY_URL, params=params,
            timeout=get_settings().reference_fetch_timeout_seconds)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ReferenceFetchError(f"GRID3 ward query failed: {exc}") from exc

    if data.get("exceededTransferLimit"):
        logger.warning(
            "GRID3 ward query for statecode=%r exceeded the transfer limit; "
            "some wards may be missing from this page.", grid3_state)

    target = normalize_name(name)
    match = next(
        (f for f in data.get("features", [])
         if normalize_name(f.get("properties", {}).get("wardname", "")) == target),
        None,
    )
    if match is None:
        return None

    props = match["properties"]
    geom = shapely_shape(match["geometry"])
    ref = props.get("wardcode") or str(props.get("FID"))
    return _persist(
        db, kind="ward", name=props.get("wardname", name),
        state_code=state_code, lga_name=props.get("lganame"),
        source="grid3_wards", source_ref=str(ref), geom=geom,
    )


def _fetch_osm_district(
    db: Session, name: str, state_code: str,
) -> ReferenceBoundary | None:
    # `~"name", i` is a case-insensitive substring match — Overpass has no
    # exact-match operator, so the real match check happens client-side below
    # against every candidate it returns.
    # district_name ultimately comes from a user-supplied project field, so
    # escape it before splicing into Overpass QL — an unescaped quote would
    # otherwise break out of the regex literal.
    escaped_name = name.replace("\\", "\\\\").replace('"', '\\"')
    query = (
        f'[out:json][timeout:{int(get_settings().reference_fetch_timeout_seconds)}];\n'
        f'relation["boundary"="administrative"]["admin_level"="7"]'
        f'["name"~"{escaped_name}", i];\n'
        f'out geom;'
    )
    try:
        resp = httpx.post(
            OVERPASS_URL, data={"data": query},
            timeout=get_settings().reference_fetch_timeout_seconds)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ReferenceFetchError(f"OSM Overpass query failed: {exc}") from exc

    target = normalize_name(name)
    match = next(
        (el for el in data.get("elements", [])
         if el.get("type") == "relation"
         and normalize_name(el.get("tags", {}).get("name", "")) == target),
        None,
    )
    if match is None:
        return None

    segments = [
        [(pt["lon"], pt["lat"]) for pt in member["geometry"]]
        for member in match.get("members", [])
        if member.get("type") == "way"
        and member.get("geometry")
        and member.get("role", "outer") == "outer"
    ]
    try:
        rings = assemble_rings(segments)
    except RingAssemblyError as exc:
        raise ReferenceFetchError(
            f"OSM relation {match.get('id')} geometry could not be "
            f"assembled into a closed boundary: {exc}"
        ) from exc

    polygons = [Polygon(ring) for ring in rings]
    geom = polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)

    return _persist(
        db, kind="district", name=match.get("tags", {}).get("name", name),
        state_code=state_code, lga_name=None,
        source="osm_admin", source_ref=str(match["id"]), geom=geom,
    )


def _persist(
    db: Session, *, kind: str, name: str, state_code: str,
    lga_name: str | None, source: str, source_ref: str, geom,
) -> ReferenceBoundary:
    try:
        geom = validate_boundary(geom)
    except BoundaryParseError as exc:
        raise ReferenceFetchError(
            f"Fetched geometry for {name!r} failed validation: {exc}") from exc

    if isinstance(geom, Polygon):
        geom = MultiPolygon([geom])

    area_km2 = area_sqm(geom, DEFAULT_METRIC_EPSG) / 1_000_000
    now = datetime.now(timezone.utc)
    name_normalized = normalize_name(name)

    # Upsert on (source, source_ref): a re-fetch of the same upstream record
    # refreshes it in place rather than creating a duplicate cache row.
    existing = db.scalar(
        select(ReferenceBoundary).where(
            ReferenceBoundary.source == source,
            ReferenceBoundary.source_ref == source_ref,
        )
    )
    if existing is not None:
        existing.name = name
        existing.name_normalized = name_normalized
        existing.state_code = state_code
        existing.lga_name = lga_name
        existing.geom = from_shape(geom, srid=4326)
        existing.area_sqkm = round(area_km2, 4)
        existing.fetched_at = now
        db.flush()
        return existing

    row = ReferenceBoundary(
        kind=kind, name=name, name_normalized=name_normalized,
        state_code=state_code, lga_name=lga_name,
        source=source, source_ref=source_ref,
        geom=from_shape(geom, srid=4326),
        area_sqkm=round(area_km2, 4), fetched_at=now,
    )
    db.add(row)
    db.flush()
    return row
