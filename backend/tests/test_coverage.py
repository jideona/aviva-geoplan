from app.domain.coverage import (DataQuality, PropertyType, assess_building,
                                 summarise_fat)


def test_surveyed_building_is_confirmed_not_estimated():
    a = assess_building("b1", 240, 0, confirmed_units=6, parcel_name="Ivy")
    assert a.quality is DataQuality.CONFIRMED
    assert a.units_low == a.units_likely == a.units_high == 6
    assert a.confidence == 1.0
    assert "surveyed" in a.basis


def test_unsurveyed_building_is_estimated_and_labelled():
    a = assess_building("b2", 45, 0)
    assert a.quality is DataQuality.ESTIMATED
    assert a.confidence < 1.0
    assert "estimated" in a.basis


def test_small_footprint_reads_as_secondary_structure():
    a = assess_building("b", 20, 0)
    assert a.property_type is PropertyType.SECONDARY


def test_a_run_of_similar_small_footprints_reads_as_terrace():
    detached = assess_building("b", 80, 0)
    terrace = assess_building("b", 80, 4)
    assert detached.property_type is PropertyType.SINGLE_HOME
    assert terrace.property_type is PropertyType.TERRACE


def test_large_footprint_reads_as_block_or_commercial():
    assert assess_building("b", 300, 0).property_type is PropertyType.APARTMENT_BLOCK
    assert assess_building("b", 600, 0).property_type is PropertyType.COMMERCIAL


def test_confirmed_and_estimated_are_kept_separate_in_the_summary():
    a = [assess_building("b1", 240, 0, confirmed_units=6, parcel_name="Ivy"),
         assess_building("b2", 45, 0),
         assess_building("b3", 50, 0)]
    fat = summarise_fat("WUY-FAT-001", 10_000, a, ["Ivy Apartments"])
    assert fat.confirmed_buildings == 1
    assert fat.estimated_buildings == 2
    assert fat.confirmed_units == 6
    # estimated units are reported as their own total, never folded in
    assert fat.estimated_units_likely == a[1].units_likely + a[2].units_likely
    assert fat.coverage_quality == "mixed"


def test_density_is_per_hectare():
    a = [assess_building(f"b{i}", 50, 0) for i in range(25)]
    fat = summarise_fat("WUY-FAT-001", 10_000, a, [])   # 1 ha
    assert fat.property_density_per_ha == 25.0


def test_a_fully_surveyed_fat_reads_as_confirmed():
    a = [assess_building(f"b{i}", 240, 0, confirmed_units=6, parcel_name="X")
         for i in range(5)]
    fat = summarise_fat("F", 10_000, a, ["X"])
    assert fat.coverage_quality == "confirmed"
