from app.domain.connectorised import (DemandPoint, fit, stock_from_lines)

# The real Aviva pre-connectorised stock.
STOCK = stock_from_lines([
    ("4way", 4, 200, 1), ("4way", 4, 300, 2),
    ("8way", 8, 50, 1), ("8way", 8, 150, 1), ("8way", 8, 250, 4), ("8way", 8, 350, 2),
    ("12way", 12, 100, 4), ("12way", 12, 150, 1), ("12way", 12, 250, 3), ("12way", 12, 350, 3),
    ("novux_12pt", 0, 250, 8), ("novux_12pt", 0, 350, 4),
])


def test_a_fat_gets_a_cable_that_reaches_and_carries():
    res = fit([DemandPoint("F1", 120, 10)], STOCK)
    assert len(res.assignments) == 1
    a = res.assignments[0]
    assert a.cable.length_m >= 120
    assert a.cable.ports >= 10


def test_tightest_fit_preserves_big_cables():
    # A small near demand should not consume a 350m 12-way.
    res = fit([DemandPoint("F1", 40, 4)], STOCK)
    a = res.assignments[0]
    assert a.cable.ports == 4 or a.cable.length_m <= 150


def test_a_fat_too_far_for_any_cable_is_unserved_with_reason():
    res = fit([DemandPoint("F1", 500, 4)], STOCK)   # nothing reaches 500m
    assert not res.assignments
    assert "reaches" in res.unserved[0].reason


def test_a_fat_needing_more_ports_than_reachable_cable_is_flagged():
    # Only a 50m 8-way reaches, but demand is 20 premises.
    small = stock_from_lines([("8way", 8, 50, 1)])
    res = fit([DemandPoint("F1", 40, 20)], small)
    assert not res.assignments
    assert "carry" in res.unserved[0].reason


def test_hardest_demand_is_served_first():
    # Two demands, one cable long enough for the far one.
    stock = stock_from_lines([("8way", 8, 100, 1), ("8way", 8, 300, 1)])
    res = fit([DemandPoint("near", 50, 4), DemandPoint("far", 280, 4)], stock)
    served = {a.fat_code: a.cable.length_m for a in res.assignments}
    assert served["far"] == 300           # far demand took the long cable
    assert served["near"] == 100


def test_leftover_and_feeders_are_reported():
    res = fit([DemandPoint("F1", 40, 4)], STOCK)
    s = res.summary()
    assert s["fats_served"] == 1
    # feeder cables never get consumed by FAT fitting
    assert any("novux" in k for k in s["cables_leftover"])


def test_summary_totals_are_consistent():
    demand = [DemandPoint(f"F{i}", 80, 8) for i in range(30)]  # exceeds 22 FATs
    res = fit(demand, STOCK)
    s = res.summary()
    assert s["fats_served"] + s["fats_unserved"] == 30
    assert s["fats_served"] <= 22          # only 22 FAT terminals exist
