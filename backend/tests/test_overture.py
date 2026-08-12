import json

import pytest

from app.domain.licences import LicenceClass
from app.domain.overture import OvertureParseError, parse_buildings

SQUARE = [[[7.4357, 9.0387], [7.4358, 9.0387], [7.4358, 9.0388],
           [7.4357, 9.0388], [7.4357, 9.0387]]]


def _doc(props: dict, coords=SQUARE) -> bytes:
    return json.dumps({
        "type": "FeatureCollection",
        "features": [{"id": "gers-1", "type": "Feature",
                      "geometry": {"type": "Polygon", "coordinates": coords},
                      "properties": props}],
    }).encode()


def test_osm_sourced_building_is_share_alike():
    data = _doc({"sources": [{"dataset": "OpenStreetMap", "license": "ODbL-1.0",
                              "record_id": "w123@1",
                              "update_time": "2025-07-12T23:00:54.000Z"}],
                 "is_underground": False})
    b = next(parse_buildings(data))
    assert b.external_id == "w123@1"
    assert b.licence_class is LicenceClass.SHARE_ALIKE
    assert b.dataset == "OpenStreetMap"


def test_google_sourced_building_is_attribution_despite_null_licence():
    data = _doc({"sources": [{"dataset": "Google Open Buildings", "license": None,
                              "record_id": "gob-9",
                              "update_time": "2023-05-01T00:00:00.000Z"}]})
    b = next(parse_buildings(data))
    assert b.licence_class is LicenceClass.ATTRIBUTION


def test_falls_back_to_feature_id_when_record_id_absent():
    b = next(parse_buildings(_doc({"sources": [{"dataset": "OpenStreetMap"}]})))
    assert b.external_id == "gers-1"


def test_unmapped_properties_are_retained_not_discarded():
    b = next(parse_buildings(_doc({"sources": [{"dataset": "OpenStreetMap",
                                                "record_id": "w1"}],
                                   "is_underground": True, "has_parts": False})))
    assert b.raw["is_underground"] is True


def test_primary_name_is_extracted():
    b = next(parse_buildings(_doc({"sources": [{"dataset": "OpenStreetMap",
                                                "record_id": "w1"}],
                                   "names": {"primary": "Wuye Market"}})))
    assert b.name == "Wuye Market"


def test_non_featurecollection_is_rejected_clearly():
    with pytest.raises(OvertureParseError, match="FeatureCollection"):
        parse_buildings(b'{"type": "Feature"}')


def test_empty_collection_is_rejected():
    with pytest.raises(OvertureParseError, match="no features"):
        parse_buildings(b'{"type": "FeatureCollection", "features": []}')


def test_road_geojson_is_rejected_with_a_pointer_to_the_right_importer():
    # The real failure: a road export silently produced zero buildings because
    # every LineString has a centroid and zero area.
    roads = json.dumps({
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {"highway": "residential"},
                      "geometry": {"type": "LineString",
                                   "coordinates": [[7.43, 9.05], [7.44, 9.06]]}}],
    }).encode()
    with pytest.raises(OvertureParseError, match="road network"):
        parse_buildings(roads)


def test_point_layer_is_rejected():
    pts = json.dumps({
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {},
                      "geometry": {"type": "Point", "coordinates": [7.43, 9.05]}}],
    }).encode()
    with pytest.raises(OvertureParseError, match="point layer"):
        parse_buildings(pts)


def test_mixed_file_with_some_polygons_is_accepted():
    mixed = json.dumps({
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {},
             "geometry": {"type": "LineString",
                          "coordinates": [[7.43, 9.05], [7.44, 9.06]]}},
            {"type": "Feature", "properties": {"sources": [{"record_id": "w1"}]},
             "geometry": {"type": "Polygon", "coordinates": SQUARE}},
        ],
    }).encode()
    assert len(list(parse_buildings(mixed))) == 1
