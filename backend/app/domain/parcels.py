"""Estate and compound perimeters — the property demarcation.

The network is built to the perimeter of each property; the drop from
perimeter to unit happens at customer signup. So the perimeter, not the
building centroid, is what determines whether a property is passed.

Aviva's own KML survey supplies these, which makes them owned data.
"""
import re
import zipfile
from dataclasses import dataclass
from io import BytesIO
from xml.etree import ElementTree

from shapely.geometry import Point, Polygon


class ParcelParseError(ValueError):
    """Message is safe to show the user."""


# Names arrive as "GC-51 [Ivy Apartments Estate Wuye]-104 units".
_GC_CODE = re.compile(r"^\s*(GC-\d+)\s*", re.I)
_UNITS = re.compile(r"[-–—\s](\d+)\s*units?\b", re.I)
_BRACKET = re.compile(r"\[([^\]]+)\]")


@dataclass
class ParsedParcel:
    name: str
    raw_name: str
    survey_code: str | None
    declared_units: int | None
    geometry: Polygon


@dataclass
class ParsedMarker:
    """A point dropped on a building during the estate count."""
    label: str
    geometry: Point


def _kml(filename: str, data: bytes) -> bytes:
    if filename.lower().endswith(".kmz"):
        try:
            with zipfile.ZipFile(BytesIO(data)) as zf:
                names = [n for n in zf.namelist() if n.lower().endswith(".kml")]
                if not names:
                    raise ParcelParseError(f"{filename}: archive holds no .kml")
                root = next((n for n in names if n.lower().endswith("doc.kml")),
                            names[0])
                return zf.read(root)
        except zipfile.BadZipFile as exc:
            raise ParcelParseError(f"{filename} is not a readable KMZ.") from exc
    return data


def _local(tag: str) -> str:
    return tag.split("}")[-1]


def _coords(text: str) -> list[tuple[float, float]]:
    out = []
    for token in text.split():
        parts = token.split(",")
        if len(parts) >= 2:
            try:
                out.append((float(parts[0]), float(parts[1])))
            except ValueError:
                continue
    return out


def clean_name(raw: str) -> tuple[str, str | None, int | None]:
    """Split 'GC-51 [Ivy Apartments Estate Wuye]-104 units' into its parts."""
    code_match = _GC_CODE.search(raw)
    code = code_match.group(1).upper() if code_match else None
    units_match = _UNITS.search(raw)
    units = int(units_match.group(1)) if units_match else None

    name = raw
    bracket = _BRACKET.search(raw)
    if bracket:
        name = bracket.group(1)
    else:
        if code_match:
            name = name[code_match.end():]
        if units_match:
            name = name[:units_match.start()]
    return name.strip(" []-–—"), code, units


def parse_parcels(filename: str, data: bytes) -> list[ParsedParcel]:
    try:
        root = ElementTree.fromstring(_kml(filename, data))
    except ElementTree.ParseError as exc:
        raise ParcelParseError(f"{filename}: KML is not well-formed — {exc}") from exc

    parcels: list[ParsedParcel] = []
    for placemark in root.iter():
        if _local(placemark.tag) != "Placemark":
            continue
        name_el = next((c for c in placemark if _local(c.tag) == "name"), None)
        raw = (name_el.text or "").strip() if name_el is not None else ""
        for node in placemark.iter():
            if _local(node.tag) != "coordinates" or not node.text:
                continue
            pts = _coords(node.text)
            if len(pts) < 4:
                break
            try:
                geom = Polygon(pts)
            except ValueError:
                break
            if not geom.is_valid:
                geom = geom.buffer(0)
            if geom.is_empty or geom.geom_type != "Polygon":
                break
            name, code, units = clean_name(raw)
            parcels.append(ParsedParcel(name=name or raw or "unnamed parcel",
                                        raw_name=raw, survey_code=code,
                                        declared_units=units, geometry=geom))
            break

    if not parcels:
        raise ParcelParseError(
            f"{filename}: no polygon found. Estate perimeters must be areas, "
            "not points or paths.")
    return parcels


def parse_markers(filename: str, data: bytes) -> list[ParsedMarker]:
    """Point markers dropped on each counted building."""
    try:
        root = ElementTree.fromstring(_kml(filename, data))
    except ElementTree.ParseError as exc:
        raise ParcelParseError(f"{filename}: KML is not well-formed — {exc}") from exc

    markers: list[ParsedMarker] = []
    for placemark in root.iter():
        if _local(placemark.tag) != "Placemark":
            continue
        name_el = next((c for c in placemark if _local(c.tag) == "name"), None)
        label = (name_el.text or "").strip() if name_el is not None else ""
        for node in placemark.iter():
            if _local(node.tag) != "coordinates" or not node.text:
                continue
            pts = _coords(node.text)
            if len(pts) == 1:
                markers.append(ParsedMarker(label=label, geometry=Point(pts[0])))
            break

    if not markers:
        raise ParcelParseError(f"{filename}: no point markers found.")
    return markers


# Placeholder names a surveyor uses when the estate name was not visible.
_PLACEHOLDER = re.compile(
    r"^\s*(unnamed|unknown|\?+|no name|private mansion|est\b|estate)\s*",
    re.I)


def looks_unnamed(name: str, survey_code: str | None = None) -> bool:
    """True where the parcel carries a placeholder rather than a real name.

    "Unnamed Est Wuye", "GC-59 [?? Estate Wuye]" and a bare survey code all
    identify a parcel without naming it.
    """
    text = (name or "").strip()
    if not text:
        return True
    if survey_code and text.upper() == survey_code.upper():
        return True
    if "??" in text or "?" == text.strip():
        return True
    return bool(_PLACEHOLDER.match(text))
