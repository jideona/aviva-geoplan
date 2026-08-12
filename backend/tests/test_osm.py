import pytest

from app.domain.osm import OsmParseError, parse_roads

OSM = """<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6">
  <node id="1" lat="9.0450" lon="7.4350"/>
  <node id="2" lat="9.0460" lon="7.4360"/>
  <node id="3" lat="9.0470" lon="7.4370"/>
  <way id="100"><nd ref="1"/><nd ref="2"/>
    <tag k="highway" v="residential"/><tag k="name" v="Ameh Ebute Street"/></way>
  <way id="101"><nd ref="2"/><nd ref="3"/>
    <tag k="highway" v="service"/></way>
  <way id="102"><nd ref="1"/><nd ref="3"/>
    <tag k="highway" v="footway"/></way>
  <way id="103"><nd ref="1"/><nd ref="2"/><tag k="building" v="yes"/></way>
</osm>"""


def test_unnamed_roads_are_imported_not_discarded():
    roads = parse_roads(OSM.encode())
    assert len(roads) == 2
    assert {r.name for r in roads} == {"Ameh Ebute Street", None}


def test_footways_and_buildings_are_excluded():
    ids = {r.external_id for r in parse_roads(OSM.encode())}
    assert "way/102" not in ids  # footway
    assert "way/103" not in ids  # building


def test_residential_outranks_service_for_addressing():
    roads = {r.highway: r for r in parse_roads(OSM.encode())}
    assert roads["residential"].class_rank < roads["service"].class_rank


def test_geojson_export_is_rejected_with_a_useful_message():
    with pytest.raises(OsmParseError, match="raw OSM data"):
        parse_roads(b'{"type": "FeatureCollection", "features": []}')


def test_document_with_no_roads_is_rejected():
    with pytest.raises(OsmParseError, match="No road geometry"):
        parse_roads(b'<osm version="0.6"><node id="1" lat="9" lon="7"/></osm>')
