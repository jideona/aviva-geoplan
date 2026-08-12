from app.domain.building_edit import CaptureSource, rules_for


def test_field_surveyed_is_owned_and_commercial():
    r = rules_for(CaptureSource.FIELD_SURVEYED)
    assert r["licence_class"] == "owned"
    assert r["verification_state"] == "field_observed"
    assert r["commercial_ready"] is True


def test_tracing_owned_drone_is_owned():
    r = rules_for(CaptureSource.TRACED_OWNED)
    assert r["licence_class"] == "owned"
    assert r["commercial_ready"] is True


def test_tracing_reference_imagery_is_restricted():
    # A rooftop traced over Esri display-only imagery is a derivative of it and
    # cannot be sold until re-sourced.
    r = rules_for(CaptureSource.TRACED_REFERENCE)
    assert r["licence_class"] == "desk_reference_restricted"
    assert r["commercial_ready"] is False


def test_manual_without_a_source_is_restricted_by_default():
    assert rules_for(CaptureSource.MANUAL)["commercial_ready"] is False
