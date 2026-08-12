from app.domain.premises_model import (Observation, Typology, band_for_units,
                                       district_total, fit, sampling_bias)

# The real Wuye February 2025 shape: independent observations, each covering
# a group of identical buildings.
WUYE = ([Observation(1, 12) for _ in range(10)]
        + [Observation(2, 9) for _ in range(6)]
        + [Observation(6, 3) for _ in range(61)]
        + [Observation(4, 4) for _ in range(12)]
        + [Observation(8, 2) for _ in range(4)]
        + [Observation(9, 1) for _ in range(12)]
        + [Observation(12, 1) for _ in range(3)]
        + [Observation(30, 1) for _ in range(10)]
        + [Observation(40, 1) for _ in range(7)]
        + [Observation(60, 1)])


def test_band_boundaries():
    assert band_for_units(1) is Typology.SINGLE
    assert band_for_units(3) is Typology.SMALL_MULTI
    assert band_for_units(6) is Typology.BLOCK
    assert band_for_units(12) is Typology.LARGE_BLOCK
    assert band_for_units(60) is Typology.TOWER


def test_fit_recovers_the_dominant_wuye_block():
    m = fit(WUYE, "wuye-2025-02")
    block = m.estimate(Typology.BLOCK)
    assert block is not None
    assert block.median == 6          # the 6-unit block dominates
    assert block.well_evidenced is True


def test_sample_size_counts_observations_not_buildings():
    # "13 buildings of 8 units" is one observation about 13 buildings.
    m = fit([Observation(units=8, building_count=13, label="Ivy Apartments")], "v1")
    band = m.estimate(Typology.BLOCK)
    assert band.sample_size == 1
    assert band.buildings_covered == 13
    assert band.replication == 13.0


def test_replication_is_reported_so_a_tight_interval_can_be_read_correctly():
    # One estate of 26 identical bungalows is one piece of evidence, and a
    # zero-width interval from it means uniform design, not corroboration.
    m = fit([Observation(units=1, building_count=26, label="Yah Wahab")], "v1")
    band = m.estimate(Typology.SINGLE)
    assert band.p25 == band.p75 == 1
    assert band.well_evidenced is False
    assert band.replication == 26.0


def test_bias_comparison_weights_by_buildings_not_observations():
    # The register is a list of buildings, so the mix must be compared in
    # buildings even though the statistics are computed per observation.
    m = fit([Observation(units=1, building_count=90, label="a"),
             Observation(units=6, building_count=10, label="b")], "v1")
    register = {Typology.SINGLE: 90, Typology.BLOCK: 10}
    bias = sampling_bias(m, register)
    assert bias["representative"] is True


def test_thin_bands_are_flagged_as_weakly_evidenced():
    m = fit(WUYE, "v1")
    assert m.estimate(Typology.LARGE_BLOCK).well_evidenced is False
    assert m.estimate(Typology.SINGLE).well_evidenced is False


def test_estate_survey_is_detected_as_unrepresentative():
    m = fit(WUYE, "v1")
    # The register is dominated by small structures the estate survey skipped.
    register = {Typology.SINGLE: 2400, Typology.BLOCK: 900,
                Typology.SMALL_MULTI: 200, Typology.TOWER: 97}
    bias = sampling_bias(m, register)
    assert bias["representative"] is False
    assert "misleading" in bias["note"]


def test_district_total_is_refused_when_sample_is_biased():
    m = fit(WUYE, "v1")
    register = {Typology.SINGLE: 2400, Typology.BLOCK: 900,
                Typology.SMALL_MULTI: 200, Typology.TOWER: 97}
    bias = sampling_bias(m, register)
    total = district_total(m, register, bias)
    assert total["available"] is False


def test_district_total_produced_when_mix_matches():
    m = fit(WUYE, "v1")
    # A register mirroring the surveyed mix.
    register = {Typology.SINGLE: 120, Typology.SMALL_MULTI: 53,
                Typology.BLOCK: 238, Typology.LARGE_BLOCK: 20,
                Typology.TOWER: 19}
    bias = sampling_bias(m, register)
    assert bias["representative"] is True
    total = district_total(m, register, bias)
    assert total["available"] is True
    assert total["interval_low"] <= total["premises_estimate"] <= total["interval_high"]


def test_matching_mix_but_one_corner_of_the_district_is_still_refused():
    # The failure this guards: a sample can mirror the register's typology mix
    # exactly and come entirely from one part of the district.
    m = fit(WUYE, "v1")
    register = {Typology.SINGLE: 120, Typology.SMALL_MULTI: 53,
                Typology.BLOCK: 238, Typology.LARGE_BLOCK: 20,
                Typology.TOWER: 19}
    bias = sampling_bias(m, register)
    assert bias["representative"] is True          # mix is fine

    coverage = {"available": True, "spatially_representative": False,
                "coverage_pct": 12.5, "cells_without_coverage": 61,
                "cells_total": 79}
    total = district_total(m, register, bias, coverage)
    assert total["available"] is False
    assert "one part of the district" in total["reason"]


def test_good_mix_and_good_coverage_produces_a_total():
    m = fit(WUYE, "v1")
    register = {Typology.SINGLE: 120, Typology.SMALL_MULTI: 53,
                Typology.BLOCK: 238, Typology.LARGE_BLOCK: 20,
                Typology.TOWER: 19}
    bias = sampling_bias(m, register)
    coverage = {"available": True, "spatially_representative": True,
                "coverage_pct": 78.0}
    total = district_total(m, register, bias, coverage)
    assert total["available"] is True
