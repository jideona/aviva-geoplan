"""Named street centreline extraction from KML and KMZ (SRD FR-STA-009).

Aviva's existing Wuye street files are per-street KMZ exports from Google Earth,
each holding one named path. These are more reliable for street naming in Wuye
than OpenStreetMap, which is thin on internal estate roads.
"""
import zipfile
from dataclasses import dataclass
from io import BytesIO
from xml.etree import ElementTree

from shapely.geometry import LineString

_KML_NS = "{http://www.opengis.net/kml/2.2}"


class StreetParseError(ValueError):
    """Message is safe to show the user."""


@dataclass
class ParsedStreet:
    name: str
    geometry: LineString


def _local(tag: str) -> str:
    return tag.split("}")[-1]


def _coords(text: str) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for token in text.split():
        parts = token.split(",")
        if len(parts) < 2:
            continue
        try:
            pts.append((float(parts[0]), float(parts[1])))
        except ValueError:
            continue
    return pts


def _kml_bytes(filename: str, data: bytes) -> bytes:
    if filename.lower().endswith(".kmz"):
        try:
            with zipfile.ZipFile(BytesIO(data)) as zf:
                kmls = [n for n in zf.namelist() if n.lower().endswith(".kml")]
                if not kmls:
                    raise StreetParseError(f"{filename}: archive contains no .kml")
                root = next((n for n in kmls if n.lower().endswith("doc.kml")), kmls[0])
                return zf.read(root)
        except zipfile.BadZipFile as exc:
            raise StreetParseError(f"{filename} is not a readable KMZ.") from exc
    return data


def parse_streets(filename: str, data: bytes,
                  fallback_name: str | None = None) -> list[ParsedStreet]:
    """Extract every named LineString. Placemarks without a name inherit the
    filename, since a per-street export often carries the name only there."""
    try:
        root = ElementTree.fromstring(_kml_bytes(filename, data))
    except ElementTree.ParseError as exc:
        raise StreetParseError(f"{filename}: KML is not well-formed — {exc}") from exc

    default = fallback_name or filename.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    out: list[ParsedStreet] = []

    for placemark in root.iter():
        if _local(placemark.tag) != "Placemark":
            continue
        name_el = next((c for c in placemark if _local(c.tag) == "name"), None)
        name = (name_el.text or "").strip() if name_el is not None else ""

        for node in placemark.iter():
            if _local(node.tag) != "LineString":
                continue
            coord_el = next((c for c in node.iter()
                             if _local(c.tag) == "coordinates"), None)
            if coord_el is None or not coord_el.text:
                continue
            pts = _coords(coord_el.text)
            if len(pts) < 2:
                continue
            out.append(ParsedStreet(name=name or default, geometry=LineString(pts)))

    if not out:
        raise StreetParseError(
            f"{filename}: no line geometry found. A street file must contain a "
            "path, not a polygon or a placemark pin."
        )
    return out
