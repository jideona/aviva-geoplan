"""OpenStreetMap XML road extraction (SRD FR-IMP-007).

Pure: bytes in, road records out.

The important design point: roads are imported whether or not they carry a
name. In Wuye the road *geometry* is largely complete while the *names* are
mostly absent, so discarding unnamed ways would throw away the network that
makes street assignment possible at all.
"""
from dataclasses import dataclass
from xml.etree import ElementTree

from shapely.geometry import LineString

# Ways that are not addressable frontage for a premises.
EXCLUDED_HIGHWAY = {"proposed", "construction", "steps", "path", "footway",
                    "cycleway", "bridleway", "corridor", "elevator"}

# Preference order when several roads are equally close. A premises is
# addressed off the residential street, not the service lane behind it.
CLASS_RANK = {
    "residential": 0, "unclassified": 1, "tertiary": 2, "secondary": 3,
    "primary": 4, "living_street": 0, "service": 5, "track": 6,
    "trunk": 7, "motorway": 8, "trunk_link": 9, "motorway_link": 9,
}
DEFAULT_RANK = 5


class OsmParseError(ValueError):
    """Message is safe to show the user."""


@dataclass
class OsmRoad:
    external_id: str
    name: str | None
    highway: str
    geometry: LineString
    oneway: bool = False
    surface: str | None = None

    @property
    def class_rank(self) -> int:
        return CLASS_RANK.get(self.highway, DEFAULT_RANK)


_WRONG_FORMAT = (
    "This looks like a GeoJSON export, not OSM XML. Export the raw OSM data "
    "from Overpass instead — a GeoJSON export commonly filters to named roads "
    "and discards most of the network, which is what street assignment needs."
)


def parse_roads(data: bytes) -> list[OsmRoad]:
    """Parse an Overpass API / JOSM OSM XML document."""
    # Detect the wrong-export mistake explicitly. It is easy to make, and the
    # generic XML parse error gives no clue what to do about it.
    if data.lstrip()[:1] in (b"{", b"["):
        raise OsmParseError(_WRONG_FORMAT)

    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise OsmParseError(f"Not well-formed OSM XML: {exc}") from exc

    if root.tag != "osm":
        raise OsmParseError(_WRONG_FORMAT)

    nodes: dict[str, tuple[float, float]] = {}
    for node in root.findall("node"):
        nid, lon, lat = node.get("id"), node.get("lon"), node.get("lat")
        if nid and lon and lat:
            nodes[nid] = (float(lon), float(lat))

    if not nodes:
        raise OsmParseError("The OSM document contains no nodes.")

    roads: list[OsmRoad] = []
    for way in root.findall("way"):
        tags = {t.get("k"): t.get("v") for t in way.findall("tag")}
        highway = tags.get("highway")
        if not highway or highway in EXCLUDED_HIGHWAY:
            continue
        pts = [nodes[nd.get("ref")] for nd in way.findall("nd")
               if nd.get("ref") in nodes]
        if len(pts) < 2:
            continue
        roads.append(OsmRoad(
            external_id=f"way/{way.get('id')}",
            name=(tags.get("name") or "").strip() or None,
            highway=highway,
            geometry=LineString(pts),
            oneway=tags.get("oneway") in {"yes", "true", "1"},
            surface=tags.get("surface"),
        ))

    if not roads:
        raise OsmParseError("No road geometry found in the OSM document.")
    return roads
