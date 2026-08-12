from app.domain.licences import LicenceClass, blocks_commercial_delivery, clearance_note
from app.domain.naming import NameSource, re_source_required, rules_for


def test_field_observed_is_owned_and_commercial_ready():
    r = rules_for(NameSource.FIELD_OBSERVED)
    assert r.licence_class is LicenceClass.OWNED
    assert r.commercial_ready is True


def test_proprietary_map_is_restricted_and_not_commercial_ready():
    r = rules_for(NameSource.PROPRIETARY_MAP)
    assert r.licence_class is LicenceClass.DESK_REFERENCE_RESTRICTED
    assert r.commercial_ready is False
    assert "re-sourced" in r.note or "replaced" in r.note


def test_authority_source_is_commercial_ready():
    assert rules_for(NameSource.AUTHORITY).commercial_ready is True


def test_open_data_names_are_share_alike():
    assert rules_for(NameSource.OPEN_DATA).licence_class is LicenceClass.SHARE_ALIKE


def test_re_sourcing_list_identifies_only_blocking_sources():
    blocked = re_source_required(["field_observed", "proprietary_map",
                                  "authority", "open_data"])
    assert blocked == ["open_data", "proprietary_map"]


def test_pilot_mix_blocks_delivery_and_says_why():
    classes = {LicenceClass.OWNED, LicenceClass.DESK_REFERENCE_RESTRICTED}
    assert blocks_commercial_delivery(classes)
    assert "re-sourced" in clearance_note(classes)


def test_clean_mix_is_cleared():
    classes = {LicenceClass.OWNED, LicenceClass.ATTRIBUTION}
    assert not blocks_commercial_delivery(classes)
    assert clearance_note(classes) == "Clear for commercial delivery."
