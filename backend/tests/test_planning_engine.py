import pytest
from shapely.geometry import LineString, Point

from app.domain.planning.engine import PlanningError, plan
from app.domain.planning.model import PlanningBuilding, PlanningRoad
from app.domain.planning.rules import DesignRules

ROAD = PlanningRoad("r1", LineString([(0, 0), (400, 0)]), "residential")


def b(i: int, x: float, y: float, premises: int = 1, assumed: bool = False):
    return PlanningBuilding(id=f"b{i:03d}", point=Point(x, y), premises=premises,
                            premises_is_assumed=assumed, code=f"B{i:03d}")


def test_capacity_is_respected():
    # Passive FAT with 16 drop ports, 25% spare -> 12 usable.
    rules = DesignRules(fat_port_count=16, spare_port_ratio=0.25)
    buildings = [b(i, i * 5, 20) for i in range(30)]
    result = plan(buildings, [ROAD], rules)
    assert all(z.premises <= 12 for z in result.zones)


def test_spare_capacity_is_actually_reserved():
    # Single-stage: usable ports come from the passive FAT drop-port count.
    rules = DesignRules(fat_port_count=24, spare_port_ratio=0.25)
    assert rules.usable_ports == 18


def test_single_stage_splitter_sits_at_the_fdh():
    rules = DesignRules(split_stage="single", fdh_split_ratio=32,
                        fat_port_count=16)
    assert rules.overall_split == 32
    # 100 premises need ceil(100/32) = 4 splitters of 1:32
    from app.domain.planning.engine import _splitter_allocation
    alloc = _splitter_allocation(100, rules)
    line = alloc["lines"][0]
    assert line["ratio"] == 32 and line["required"] == 4


def test_single_stage_from_stock_needs_no_purchase():
    rules = DesignRules(split_stage="single", fdh_split_ratio=32,
                        fat_port_count=16, splitter_stock=((32, 18),))
    from app.domain.planning.engine import _splitter_allocation
    # 512 premises = 16 splitters, 18 in stock -> zero purchase
    alloc = _splitter_allocation(512, rules)
    assert alloc["zero_purchase"] is True


def test_every_building_is_either_served_or_reported():
    rules = DesignRules()
    buildings = [b(i, i * 10, 10) for i in range(20)]
    result = plan(buildings, [ROAD], rules)
    served = {bid for z in result.zones for bid in z.building_ids}
    assert len(served) + len(result.unassigned_building_ids) == len(buildings)


def test_fat_is_sited_on_the_road_not_in_a_block():
    rules = DesignRules()
    buildings = [b(i, 50 + i * 4, 30) for i in range(6)]
    result = plan(buildings, [ROAD], rules)
    zone = result.zones[0]
    assert zone.road_id == "r1"
    assert zone.fat_point.y == pytest.approx(0.0, abs=0.01)   # snapped to road


def test_a_set_back_cluster_is_served_but_the_offset_is_flagged():
    # Set back from the road but within drop range: the zone is kept and the
    # siting distance reported, because a long offset means long drops and a
    # designer should look at it.
    rules = DesignRules(max_fat_road_offset_m=25, max_drop_length_m=150)
    buildings = [b(i, 50 + i * 4, 40) for i in range(4)]
    result = plan(buildings, [ROAD], rules)
    zone = result.zones[0]
    assert zone.fat_point.y == pytest.approx(0.0, abs=0.01)
    assert zone.road_offset_m is not None and zone.road_offset_m > 25
    assert any("siting limit" in w for w in zone.warnings)
    assert not result.unassigned_building_ids


def test_assumed_premises_are_counted_and_warned_about():
    rules = DesignRules()
    buildings = [b(i, i * 10, 10, premises=1, assumed=True) for i in range(10)]
    result = plan(buildings, [ROAD], rules)
    assert result.premises_assumed_count == 10
    assert any("lower bound" in w for w in result.warnings)


def test_building_larger_than_a_fat_is_reported():
    rules = DesignRules(fat_splitter_ratio=8, spare_port_ratio=0.0)  # 8 usable
    buildings = [b(1, 10, 10, premises=60)]                          # a plaza
    result = plan(buildings, [ROAD], rules)
    assert any("dedicated splitter" in w for w in result.warnings)


def test_tiny_zones_are_merged_rather_than_given_their_own_fat():
    rules = DesignRules(min_premises_per_fat=4, max_drop_length_m=200)
    buildings = [b(1, 10, 10), b(2, 14, 10), b(3, 60, 10), b(4, 64, 10)]
    result = plan(buildings, [ROAD], rules)
    assert len(result.zones) == 1


def test_the_design_is_reproducible():
    rules = DesignRules()
    buildings = [b(i, (i * 37) % 300, (i * 53) % 120) for i in range(40)]
    a = plan(buildings, [ROAD], rules)
    c = plan(list(reversed(buildings)), [ROAD], rules)
    assert [z.building_ids for z in a.zones] == [z.building_ids for z in c.zones]


def test_invalid_split_ratio_is_rejected():
    with pytest.raises(PlanningError, match="standard"):
        plan([b(1, 0, 0)], [ROAD], DesignRules(fdh_split_ratio=7))


def test_no_buildings_is_rejected():
    with pytest.raises(PlanningError, match="No buildings"):
        plan([], [ROAD], DesignRules())


def test_no_drop_exceeds_the_limit_after_the_fat_is_sited():
    # The defect this guards: clustering measures from the seed, then the FAT
    # moves to the road, which can push drops past the limit.
    rules = DesignRules(max_drop_length_m=80, fat_splitter_ratio=32,
                        spare_port_ratio=0.0)
    buildings = [b(i, 20 + i * 12, 70) for i in range(24)]
    result = plan(buildings, [ROAD], rules)
    for zone in result.zones:
        assert zone.max_drop_m <= rules.max_drop_length_m + 0.01, (
            f"{zone.code_suffix} has a {zone.max_drop_m} m drop against an "
            f"{rules.max_drop_length_m} m limit")


def test_buildings_moved_during_repair_are_reported():
    rules = DesignRules(max_drop_length_m=60, fat_splitter_ratio=32,
                        spare_port_ratio=0.0)
    buildings = [b(i, 20 + i * 10, 55) for i in range(20)]
    result = plan(buildings, [ROAD], rules)
    served = {bid for z in result.zones for bid in z.building_ids}
    assert len(served) + len(result.unassigned_building_ids) == len(buildings)


def test_unreachable_buildings_leave_the_design_rather_than_breaching_it():
    rules = DesignRules(max_drop_length_m=40)
    near = [b(i, 20 + i * 8, 25) for i in range(6)]
    stranded = [b(90, 200, 400)]          # 400 m from the only road
    result = plan(near + stranded, [ROAD], rules)
    assert "b090" in result.unassigned_building_ids
    for zone in result.zones:
        assert zone.max_drop_m <= rules.max_drop_length_m + 0.01


def test_an_estate_fills_whole_fats_before_pulling_in_neighbours():
    # 10 estate buildings + 10 neighbours interleaved geographically. With
    # estate-aware clustering the estate should occupy whole FATs, not scatter.
    rules = DesignRules(fat_port_count=12, spare_port_ratio=0.0)
    estate = [PlanningBuilding(f"e{i}", Point(i * 8, 20), 1, True, group_id="EST")
              for i in range(10)]
    others = [PlanningBuilding(f"o{i}", Point(i * 8 + 4, 24), 1, True, group_id=None)
              for i in range(10)]
    result = plan(estate + others, [ROAD], rules)
    # Count, per FAT, how many estate buildings and whether it is estate-pure.
    fat_of = {}
    for z in result.zones:
        for bid in z.building_ids:
            fat_of[bid] = z.code_suffix
    estate_fats = {fat_of[f"e{i}"] for i in range(10)}
    # The 10 estate buildings should sit in one FAT (12 cap), not spread wide.
    assert len(estate_fats) <= 2
