from app.domain.attribution import ExportPurpose, SourceEntry, build

OSM = SourceEntry("Overture — OpenStreetMap", "ODbL-1.0", "share_alike", 1703)
GOOGLE = SourceEntry("Overture — Google Open Buildings", None, "attribution", 1858)
FIELD = SourceEntry("Aviva field survey", "Proprietary", "owned", 42)
PILOT_NAMES = SourceEntry("Street names — proprietary map", None,
                          "desk_reference_restricted", 121)


def test_internal_export_is_never_blocked():
    m = build("Wuye", "now", ExportPurpose.INTERNAL, [OSM, GOOGLE, PILOT_NAMES])
    assert m.blocked is False


def test_commercial_export_blocked_by_share_alike():
    m = build("Wuye", "now", ExportPurpose.COMMERCIAL, [OSM, GOOGLE])
    assert m.blocked is True
    assert "share-alike" in (m.reason or "")


def test_commercial_export_blocked_by_pilot_street_names():
    m = build("Wuye", "now", ExportPurpose.COMMERCIAL, [GOOGLE, PILOT_NAMES])
    assert m.blocked is True
    assert "desk reference restricted" in (m.reason or "")


def test_clean_sources_clear_commercial_export():
    m = build("Wuye", "now", ExportPurpose.COMMERCIAL, [GOOGLE, FIELD])
    assert m.blocked is False
    assert m.reason is None


def test_client_review_is_not_the_commercial_gate():
    m = build("Wuye", "now", ExportPurpose.CLIENT_REVIEW, [OSM, PILOT_NAMES])
    assert m.blocked is False


def test_manifest_lists_every_source_with_counts():
    m = build("Wuye", "now", ExportPurpose.INTERNAL, [OSM, GOOGLE, FIELD])
    text = m.as_text()
    assert "1,703" in text and "1,858" in text
    assert len(m.attribution_lines()) == 3


def test_unknown_licence_class_is_treated_as_restricted():
    weird = SourceEntry("Vendor X", None, "something_new", 5)
    m = build("Wuye", "now", ExportPurpose.COMMERCIAL, [weird])
    assert m.blocked is True
