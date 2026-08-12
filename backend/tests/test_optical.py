from app.domain.optical import (OpticalParams, PathSpec, Verdict, compute)

P = OpticalParams()   # XGS-PON N1: 4 dBm launch, -28 sensitivity, 32 dB budget


def test_single_stage_1_32_passes_on_a_short_run():
    path = PathSpec(feeder_m=300, distribution_m=200, drop_m=50,
                    splitter_ratios=[32])
    r = compute(path, P)
    assert r.verdict is Verdict.PASS
    assert r.design_margin_db > 0


def test_two_stage_1_32_matches_single_stage_within_a_fraction():
    # 1:4 (7.3) + 1:8 (10.5) = 17.8 vs single 1:32 (17.5) — near identical.
    single = compute(PathSpec(400, 300, 50, [32]), P)
    two = compute(PathSpec(400, 300, 50, [4, 8]), P)
    assert abs(single.total_loss_db - two.total_loss_db) < 0.5


def test_1_64_is_tighter_than_1_32():
    # 1:8 + 1:8 = 21 dB, materially worse than 1:32's 17.5.
    a = compute(PathSpec(400, 300, 50, [32]), P)
    b = compute(PathSpec(400, 300, 50, [8, 8]), P)
    assert b.total_loss_db > a.total_loss_db + 3


def test_a_long_run_eventually_fails():
    # Push fibre out far enough to break the budget.
    r = compute(PathSpec(feeder_m=20000, distribution_m=15000, drop_m=100,
                         splitter_ratios=[32]), P)
    assert r.verdict is Verdict.FAIL
    assert "exceeds" in r.reason


def test_thin_margin_is_a_warning_not_a_pass():
    # A high required margin turns a positive but small headroom into a warning.
    tight = OpticalParams(required_margin_db=8.0)
    r = compute(PathSpec(2000, 2000, 100, [32]), tight)
    assert r.design_margin_db > 0            # not a fail
    assert r.verdict is Verdict.WARNING      # but below the required margin


def test_every_value_is_configurable():
    # No hard-coded attenuation: change it and the total moves.
    base = compute(PathSpec(1000, 0, 0, [32]), OpticalParams(fibre_db_per_km=0.35))
    hi = compute(PathSpec(1000, 0, 0, [32]), OpticalParams(fibre_db_per_km=0.5))
    assert hi.total_loss_db > base.total_loss_db


def test_elements_sum_to_the_total():
    r = compute(PathSpec(500, 300, 50, [4, 8]), P)
    assert abs(sum(e.loss_db for e in r.elements) - r.total_loss_db) < 1e-6
