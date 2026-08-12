from app.domain.equipment_envelope import envelope

STOCK = {32: 18, 8: 78, 4: 20}          # 1:4 procured
NO_1_4 = {32: 18, 8: 78, 4: 0}


def test_connectorised_core_is_zero_purchase():
    e = envelope(STOCK, 208, 22)
    core = e["phases"][0]
    assert core["premises"] == 208
    assert core["zero_purchase"] is True     # 7 x 1:32 <= 18


def test_procured_1_4_gives_a_two_stage_1_32_extension():
    e = envelope(STOCK, 208, 22, 16)
    ext = e["phases"][1]
    assert "1:32" in ext["architecture"]
    # Phase 1 takes 7 ports; Phase 2 gets the remaining 9 x 32 = 288.
    assert ext["premises"] == 288


def test_without_1_4_it_falls_back_to_1_64():
    e = envelope(NO_1_4, 208, 22, 16)
    assert "1:64" in e["phases"][1]["architecture"]


def test_both_phases_share_one_olt_port_budget():
    # The correction: 720 was wrong; on one 16-port OLT it is 208 + 288 = 496.
    e = envelope(STOCK, 208, 22, 16)
    assert e["combined_premises"] == 496
    assert e["pon_ports_used"] == 16
    assert e["one_olt_ceiling"] is True


def test_a_larger_olt_lifts_the_ceiling():
    e = envelope(STOCK, 208, 22, 32)
    assert e["combined_premises"] > 496


def test_the_1_64_fallback_is_documented_when_1_4_is_stocked():
    e = envelope(STOCK, 208, 22, 16)
    assert "1:64" in e["fallback"]


def test_phase_two_passive_plant_is_a_purchase():
    e = envelope(STOCK, 208, 22, 16)
    assert e["phases"][1]["zero_purchase"] is False
    assert "cable" in e["phases"][1]["purchase_needed"]
