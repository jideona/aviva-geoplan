import zipfile
from io import BytesIO

import pytest

from app.domain.streets_kml import StreetParseError, parse_streets

KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark>
<name>Ameh Ebute Street</name>
<LineString><coordinates>
7.4322,9.0443,0 7.4380,9.0470,0 7.4441,9.0503,0
</coordinates></LineString>
</Placemark></Document></kml>"""

UNNAMED = KML.replace("<name>Ameh Ebute Street</name>", "")


def test_named_placemark():
    streets = parse_streets("whatever.kml", KML.encode())
    assert len(streets) == 1
    assert streets[0].name == "Ameh Ebute Street"
    assert len(streets[0].geometry.coords) == 3


def test_unnamed_placemark_inherits_the_filename():
    # Aviva's per-street KMZ exports often carry the name only in the filename.
    streets = parse_streets("Ken Nnamani Cres.kmz", _kmz(UNNAMED))
    assert streets[0].name == "Ken Nnamani Cres"


def test_kmz_archive():
    streets = parse_streets("Ameh Ebute Street.kmz", _kmz(KML))
    assert streets[0].name == "Ameh Ebute Street"


def test_file_without_a_line_explains_the_problem():
    point = ("""<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2">"""
             """<Placemark><name>NOC</name><Point>"""
             """<coordinates>7.45,9.06</coordinates></Point></Placemark></kml>""")
    with pytest.raises(StreetParseError, match="no line geometry"):
        parse_streets("NOC.kml", point.encode())


def _kmz(kml: str) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("doc.kml", kml)
    return buf.getvalue()
