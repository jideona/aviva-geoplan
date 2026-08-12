from app.domain.licences import (LicenceClass, attribution_required,
                                 blocks_commercial_delivery, classify)


def test_osm_odbl_is_share_alike():
    assert classify("ODbL-1.0", "OpenStreetMap") is LicenceClass.SHARE_ALIKE


def test_google_open_buildings_null_licence_falls_back_to_dataset():
    # Overture emits a null licence for Google Open Buildings. The upstream
    # grant is CC BY 4.0, so it must not be treated as unrestricted.
    assert classify(None, "Google Open Buildings") is LicenceClass.ATTRIBUTION


def test_microsoft_is_share_alike():
    assert classify(None, "Microsoft ML Buildings") is LicenceClass.SHARE_ALIKE


def test_unknown_source_is_restricted_not_permissive():
    assert classify(None, "Some Vendor") is LicenceClass.PROPRIETARY_RESTRICTED
    assert classify(None, None) is LicenceClass.PROPRIETARY_RESTRICTED


def test_share_alike_blocks_commercial_delivery():
    assert blocks_commercial_delivery({LicenceClass.SHARE_ALIKE,
                                       LicenceClass.ATTRIBUTION})
    assert not blocks_commercial_delivery({LicenceClass.ATTRIBUTION,
                                           LicenceClass.OWNED})


def test_owned_only_needs_no_attribution():
    assert not attribution_required({LicenceClass.OWNED})
    assert attribution_required({LicenceClass.OWNED, LicenceClass.ATTRIBUTION})
