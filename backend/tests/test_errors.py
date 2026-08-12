from app.core.errors import audience_hint, classify, envelope


def test_5xx_is_an_admin_fault():
    assert classify(500) == "admin"
    assert classify(503) == "admin"
    assert "system fault" in audience_hint(500)


def test_4xx_is_a_user_matter():
    for code in (400, 404, 409, 413, 422, 451):
        assert classify(code) == "user"


def test_permission_and_session_get_specific_hints():
    assert "administrator" in audience_hint(403)
    assert "sign in" in audience_hint(401)


def test_envelope_carries_kind_and_remedy():
    e = envelope(400, "Boundary is invalid.", "Reproject to EPSG:4326.")
    assert e["detail"] == "Boundary is invalid."
    assert e["kind"] == "user"
    assert e["remedy"] == "Reproject to EPSG:4326."
