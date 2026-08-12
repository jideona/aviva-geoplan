import zipfile
from io import BytesIO

import pytest

from app.domain.parcels import (ParcelParseError, clean_name, parse_markers,
                                parse_parcels)

POLY = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Placemark><name>GC-51 [Ivy Apartments Estate Wuye]-104 units</name><Polygon>
<outerBoundaryIs><LinearRing><coordinates>
7.440,9.050,0 7.442,9.050,0 7.442,9.052,0 7.440,9.052,0 7.440,9.050,0
</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
<Placemark><name>Yah Wahab Estate Phase2</name><Polygon>
<outerBoundaryIs><LinearRing><coordinates>
7.443,9.050,0 7.445,9.050,0 7.445,9.052,0 7.443,9.052,0 7.443,9.050,0
</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
</Document></kml>"""

PTS = """<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2">
<Placemark><name>1</name><Point><coordinates>7.4410,9.0510</coordinates></Point></Placemark>
<Placemark><name>2</name><Point><coordinates>7.4415,9.0512</coordinates></Point></Placemark>
</kml>"""


def test_survey_code_name_and_units_are_separated():
    name, code, units = clean_name("GC-51 [Ivy Apartments Estate Wuye]-104 units")
    assert name == "Ivy Apartments Estate Wuye"
    assert code == "GC-51"
    assert units == 104


def test_units_written_after_the_bracket_are_found():
    _, _, units = clean_name("GC-52 [Omako Estate Wuye] 63 Units")
    assert units == 63


def test_a_plain_name_survives_untouched():
    name, code, units = clean_name("Yah Wahab Estate Phase2")
    assert name == "Yah Wahab Estate Phase2"
    assert code is None and units is None


def test_perimeters_parse_with_geometry():
    parcels = parse_parcels("perimeters.kml", POLY.encode())
    assert len(parcels) == 2
    ivy = next(p for p in parcels if p.survey_code == "GC-51")
    assert ivy.declared_units == 104
    assert ivy.geometry.geom_type == "Polygon"


def test_kmz_archive_is_read():
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("doc.kml", POLY)
    assert len(parse_parcels("perimeters.kmz", buf.getvalue())) == 2


def test_markers_parse_as_points():
    markers = parse_markers("counts.kml", PTS.encode())
    assert [m.label for m in markers] == ["1", "2"]
    assert markers[0].geometry.geom_type == "Point"


def test_a_point_file_is_rejected_by_the_perimeter_parser():
    with pytest.raises(ParcelParseError, match="must be areas"):
        parse_parcels("counts.kml", PTS.encode())
