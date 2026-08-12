"""Overture Maps building parsing (SRD FR-IMP-005).

Pure: bytes in, normalised records out. No I/O, no database.

Overture delivers buildings already deduplicated across its contributing
sources — a building carries one source attribution rather than a merge of
several. Consequently Google Open Buildings must NOT be imported separately
against an Overture load; it is already present within it.
"""
import json
from dataclasses import dataclass, field
from typing import Any, Iterator

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from app.domain.licences import LicenceClass, classify


class OvertureParseError(ValueError):
    """Message is safe to show the user."""


@dataclass
class OvertureBuilding:
    geometry: BaseGeometry
    external_id: str
    dataset: str | None
    licence: str | None
    licence_class: LicenceClass
    source_update: str | None
    # Attributes are sparse in practice; all are optional by design.
    num_floors: int | None = None
    height_m: float | None = None
    building_class: str | None = None
    subtype: str | None = None
    name: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def _name_of(props: dict) -> str | None:
    names = props.get("names")
    if isinstance(names, dict):
        primary = names.get("primary")
        if isinstance(primary, str):
            return primary
    return None


def parse_buildings(data: bytes) -> Iterator[OvertureBuilding]:
    """Parse an Overture buildings GeoJSON export.

    Validation is eager: a malformed or empty file raises here rather than
    partway through iteration, so a caller never begins a partial import
    against a file that was never going to work.

    Read as a whole document. A streaming reader replaces this when exports
    exceed available memory (SRD FR-IMP-010); at district scale the whole file
    is a few megabytes.
    """
    try:
        doc = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OvertureParseError(f"File is not valid GeoJSON: {exc}") from exc

    if doc.get("type") != "FeatureCollection":
        raise OvertureParseError(
            "Expected a GeoJSON FeatureCollection from the Overture export."
        )

    features = doc.get("features") or []
    if not features:
        raise OvertureParseError("The export contains no features.")

    _reject_wrong_geometry(features)
    return _iter_buildings(features)


def _reject_wrong_geometry(features: list, sample: int = 200) -> None:
    """Fail fast when the file is not buildings.

    Without this, a road network passes straight through: every LineString has
    a centroid and zero area, so the boundary and minimum-size filters silently
    discard all of it and the import reports success with nothing created.
    """
    kinds: dict[str, int] = {}
    for feature in features[:sample]:
        geometry = feature.get("geometry") or {}
        kind = geometry.get("type")
        if kind:
            kinds[kind] = kinds.get(kind, 0) + 1
    if not kinds:
        raise OvertureParseError("No feature in this file has geometry.")

    polygons = kinds.get("Polygon", 0) + kinds.get("MultiPolygon", 0)
    if polygons:
        return

    dominant = max(kinds, key=lambda k: kinds[k])
    hint = ""
    if dominant in {"LineString", "MultiLineString"}:
        hint = (" This looks like a road network. Import it under "
                "'OSM road network' or 'Named centrelines' instead.")
    elif dominant == "Point":
        hint = " This looks like a point layer, not building footprints."
    raise OvertureParseError(
        f"This file contains {dominant} geometry, but building footprints must "
        f"be polygons.{hint}"
    )


def _iter_buildings(features: list) -> Iterator[OvertureBuilding]:
    for feature in features:
        geometry = feature.get("geometry")
        if not geometry:
            continue
        try:
            geom = shape(geometry)
        except (TypeError, ValueError):
            continue
        if geom.is_empty:
            continue
        if not geom.is_valid:
            geom = geom.buffer(0)
            if geom.is_empty or not geom.is_valid:
                continue

        props = feature.get("properties") or {}
        sources = props.get("sources") or []
        primary = sources[0] if sources else {}
        dataset = primary.get("dataset")
        licence = primary.get("license")

        # Prefer the upstream record id — it is stable across Overture releases
        # in a way the Overture GERS id is not guaranteed to be.
        external_id = primary.get("record_id") or feature.get("id") or ""
        if not external_id:
            continue

        yield OvertureBuilding(
            geometry=geom,
            external_id=str(external_id),
            dataset=dataset,
            licence=licence,
            licence_class=classify(licence, dataset),
            source_update=primary.get("update_time"),
            num_floors=props.get("num_floors"),
            height_m=props.get("height"),
            building_class=props.get("class"),
            subtype=props.get("subtype"),
            name=_name_of(props),
            raw={k: v for k, v in props.items()
                 if k not in {"sources", "names"}},
        )
