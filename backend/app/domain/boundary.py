"""Boundary file parsing and validation (SRD FR-PRJ-004 to FR-PRJ-006).

Pure functions: bytes in, shapely geometry out. No I/O, no database.

GeoJSON and KML/KMZ are parsed directly rather than through a GDAL driver, so
that boundary upload does not depend on which optional drivers a given Fiona
wheel was built with.
"""
import json
import re
import zipfile
from io import BytesIO
from xml.etree import ElementTree

from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

_KML_NS = {"k": "http://www.opengis.net/kml/2.2"}
_WS = re.compile(r"\s+")


class BoundaryParseError(ValueError):
    """Raised with a message intended to be shown to the user."""


def parse_boundary(filename: str, data: bytes) -> BaseGeometry:
    name = filename.lower()
    if name.endswith((".geojson", ".json")):
        geom = _from_geojson(data)
    elif name.endswith(".kml"):
        geom = _from_kml(data)
    elif name.endswith(".kmz"):
        geom = _from_kml(_kml_from_kmz(data))
    else:
        raise BoundaryParseError(
            f"Unsupported boundary format {filename!r}. Use GeoJSON, KML or KMZ."
        )
    return validate_boundary(geom)


def _kml_from_kmz(data: bytes) -> bytes:
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            kmls = [n for n in zf.namelist() if n.lower().endswith(".kml")]
            if not kmls:
                raise BoundaryParseError("KMZ archive contains no .kml file.")
            # doc.kml is the conventional root; otherwise take the first.
            root = next((n for n in kmls if n.lower().endswith("doc.kml")), kmls[0])
            return zf.read(root)
    except zipfile.BadZipFile as exc:
        raise BoundaryParseError("KMZ file is not a readable archive.") from exc


def _from_geojson(data: bytes) -> BaseGeometry:
    try:
        doc = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BoundaryParseError(f"File is not valid GeoJSON: {exc}") from exc

    kind = doc.get("type")
    try:
        if kind == "FeatureCollection":
            geoms = [shape(f["geometry"]) for f in doc["features"] if f.get("geometry")]
        elif kind == "Feature":
            geoms = [shape(doc["geometry"])]
        elif kind:
            geoms = [shape(doc)]
        else:
            raise BoundaryParseError("GeoJSON has no 'type' member.")
    except (KeyError, TypeError, ValueError) as exc:
        raise BoundaryParseError(f"GeoJSON geometry could not be read: {exc}") from exc

    if not geoms:
        raise BoundaryParseError("GeoJSON contains no geometry.")
    return unary_union(geoms)


def _coords(text: str) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for token in _WS.sub(" ", text.strip()).split(" "):
        if not token:
            continue
        parts = token.split(",")
        if len(parts) < 2:
            raise BoundaryParseError(f"Malformed KML coordinate {token!r}.")
        out.append((float(parts[0]), float(parts[1])))  # drop altitude
    return out


def _from_kml(data: bytes) -> BaseGeometry:
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise BoundaryParseError(f"KML is not well-formed XML: {exc}") from exc

    # Namespaced and bare KML are both common in the wild.
    polys: list[Polygon] = []
    for ns in (_KML_NS, {}):
        prefix = "k:" if ns else ""
        found = root.findall(f".//{prefix}Polygon", ns) if ns else root.findall(".//Polygon")
        for poly in found:
            outer_path = (f".//{prefix}outerBoundaryIs//{prefix}coordinates"
                          if ns else ".//outerBoundaryIs//coordinates")
            inner_path = (f".//{prefix}innerBoundaryIs//{prefix}coordinates"
                          if ns else ".//innerBoundaryIs//coordinates")
            outer = poly.find(outer_path, ns) if ns else poly.find(outer_path)
            if outer is None or not outer.text:
                continue
            inners = (poly.findall(inner_path, ns) if ns else poly.findall(inner_path))
            holes = [_coords(i.text) for i in inners if i.text]
            try:
                polys.append(Polygon(_coords(outer.text), holes))
            except ValueError as exc:
                raise BoundaryParseError(f"KML polygon is not valid: {exc}") from exc
        if polys:
            break

    if not polys:
        raise BoundaryParseError(
            "No polygon found in the KML. A project boundary must be a polygon, "
            "not a point, path or placemark."
        )
    return unary_union(polys) if len(polys) > 1 else polys[0]


def validate_boundary(geom: BaseGeometry) -> BaseGeometry:
    """Repair where unambiguous, reject where not (FR-PRJ-005)."""
    if geom.is_empty:
        raise BoundaryParseError("Boundary geometry is empty.")

    if not geom.is_valid:
        repaired = geom.buffer(0)
        if repaired.is_empty or not repaired.is_valid:
            raise BoundaryParseError(
                "Boundary geometry is invalid and could not be repaired. It is "
                "most likely self-intersecting."
            )
        geom = repaired

    if not isinstance(geom, (Polygon, MultiPolygon)):
        raise BoundaryParseError(
            f"Boundary must be a polygon; found {geom.geom_type}."
        )

    minx, miny, maxx, maxy = geom.bounds
    if not (-180 <= minx <= 180 and -180 <= maxx <= 180 and -90 <= miny <= 90
            and -90 <= maxy <= 90):
        raise BoundaryParseError(
            "Coordinates are outside the valid longitude/latitude range. The file "
            "is most likely in a projected CRS; reproject it to EPSG:4326 first."
        )
    return geom
