from app.domain.connectorised import DemandPoint, fit, stock_from_lines
from app.domain.pilot import FatDemand, build_pilot

STOCK = {32: 18, 8: 78, 4: 20}
CONN = stock_from_lines([
    ("8way", 8, 250, 4), ("8way", 8, 350, 2),
    ("12way", 12, 250, 3), ("12way", 12, 350, 3),
])


def _demand(n, base_dist=100, premises=8):
    return [FatDemand(f"FAT-{i:03d}", base_dist + i * 20, premises)
            for i in range(n)]


def test_pilot_splits_into_two_phases_on_one_olt():
    demand = _demand(30)
    conn = fit([DemandPoint(d.fat_code, d.distance_from_noc_m, d.premises)
                for d in demand], CONN)
    plan = build_pilot(demand, STOCK, conn, olt_pon_ports=16)
    assert plan.phase1_fats           # connectorised placed some
    assert plan.phase2_fats           # conventional filled the rest
    # never exceed the OLT
    import math
    ports = (math.ceil(plan.phase1_premises / 32)
             + math.ceil(plan.phase2_premises / 32))
    assert ports <= 16


def test_connectorised_fats_come_first_by_distance():
    demand = _demand(20)
    conn = fit([DemandPoint(d.fat_code, d.distance_from_noc_m, d.premises)
                for d in demand], CONN)
    plan = build_pilot(demand, STOCK, conn, 16)
    # phase 1 FATs are all nearer than the farthest phase 2 FAT
    if plan.phase1_fats and plan.phase2_fats:
        assert max(f.route_m for f in plan.phase1_fats) <= \
               max(f.route_m for f in plan.phase2_fats)


def test_equipment_schedule_only_buys_1_4():
    demand = _demand(25)
    conn = fit([DemandPoint(d.fat_code, d.distance_from_noc_m, d.premises)
                for d in demand], CONN)
    plan = build_pilot(demand, STOCK, conn, 16)
    buys = {l["item"]: l["buy"] for l in plan.equipment["splitters"]}
    assert buys["1:32 splitter"] == 0
    assert buys["1:8 splitter"] == 0
    # 1:4 may or may not need a top-up depending on phase-2 size, but is the
    # only line that ever does
    assert all(v == 0 for k, v in buys.items() if k != "1:4 splitter")


def test_full_olt_warns_about_a_second_olt():
    demand = _demand(60, premises=12)   # more than one OLT can serve
    conn = fit([DemandPoint(d.fat_code, d.distance_from_noc_m, d.premises)
                for d in demand], CONN)
    plan = build_pilot(demand, STOCK, conn, 16)
    assert any("second OLT" in w for w in plan.warnings)
