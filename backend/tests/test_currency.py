from datetime import date

from app.domain.currency import (Currency, age_years, classify,
                                 requires_field_check, survey_priority)

TODAY = date(2026, 7, 21)


def test_age_in_years():
    assert age_years(date(2023, 5, 1), TODAY) == 3.22
    assert age_years(None, TODAY) is None


def test_google_open_buildings_2023_capture_is_stale():
    # 57% of the Wuye register sits here.
    assert classify(date(2023, 5, 1), TODAY) is Currency.STALE


def test_recent_osm_edit_is_current():
    assert classify(date(2026, 5, 1), TODAY) is Currency.CURRENT


def test_2019_records_are_obsolete():
    assert classify(date(2019, 12, 1), TODAY) is Currency.OBSOLETE


def test_missing_date_is_unknown_and_top_priority():
    assert classify(None, TODAY) is Currency.UNKNOWN
    assert survey_priority(None, TODAY) == 1


def test_obsolete_outranks_stale_for_survey():
    assert survey_priority(date(2019, 1, 1), TODAY) < survey_priority(
        date(2023, 5, 1), TODAY)


def test_field_check_required_beyond_two_years():
    assert not requires_field_check(date(2025, 7, 1), TODAY)
    assert requires_field_check(date(2023, 5, 1), TODAY)
    assert requires_field_check(None, TODAY)
