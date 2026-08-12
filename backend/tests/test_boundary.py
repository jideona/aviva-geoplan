import json
import zipfile
from io import BytesIO

import pytest

from app.domain.boundary import BoundaryParseError, parse_boundary

WUYE_RING = [(7.43, 9.05), (7.47, 9.05), (7.47, 9.09), (7.43, 9.09), (7.43, 9.05)]

KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><Polygon>
<outerBoundaryIs><LinearRing><coordinates>
7.43,9.05,0 7.47,9.05,0 7.47,9.09,0 7.43,9.09,0 7.43,9.05,0
</coordinates></LinearRing></outerBoundaryIs>
</Polygon></Placemark></Document></kml>"""


def _geojson(ring=WUYE_RING) -> bytes:
    return json.dumps({
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {},
                      "geometry": {"type": "Polygon", "coordinates": [ring]}}],
    }).encode()


def test_geojson_feature_collection():
    geom = parse_boundary("wuye.geojson", _geojson())
    assert geom.geom_type == "Polygon"
    assert geom.bounds == pytest.approx((7.43, 9.05, 7.47, 9.09))


def test_kml_polygon_with_altitude_component():
    geom = parse_boundary("wuye.kml", KML.encode())
    assert geom.geom_type == "Polygon"
    assert geom.bounds == pytest.approx((7.43, 9.05, 7.47, 9.09))


def test_kmz_archive():
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("doc.kml", KML)
    geom = parse_boundary("wuye.kmz", buf.getvalue())
    assert geom.geom_type == "Polygon"


def test_projected_coordinates_are_rejected_with_a_useful_message():
    # UTM metres, not degrees — the most common real-world upload mistake.
    ring = [(320000, 1000000), (321000, 1000000), (321000, 1001000),
            (320000, 1001000), (320000, 1000000)]
    with pytest.raises(BoundaryParseError, match="reproject"):
        parse_boundary("wuye.geojson", _geojson(ring))


def test_self_intersecting_polygon_is_repaired_or_rejected_clearly():
    bowtie = [(0, 0), (2, 2), (2, 0), (0, 2), (0, 0)]
    try:
        geom = parse_boundary("bowtie.geojson", _geojson(bowtie))
        assert geom.is_valid
    except BoundaryParseError as exc:
        assert "self-intersecting" in str(exc)


def test_unsupported_format_is_named_in_the_error():
    with pytest.raises(BoundaryParseError, match="Unsupported"):
        parse_boundary("boundary.dwg", b"whatever")


def test_kml_without_a_polygon_explains_the_problem():
    point_kml = ("""<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2">"""
                 """<Placemark><Point><coordinates>7.45,9.06</coordinates></Point>"""
                 """</Placemark></kml>""")
    with pytest.raises(BoundaryParseError, match="polygon"):
        parse_boundary("point.kml", point_kml.encode())
