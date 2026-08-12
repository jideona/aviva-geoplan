import pytest

from app.domain.identifiers import (building_code, compound_code, district_prefix,
                                    premises_code, street_code)


def test_prefix_from_district_name():
    assert district_prefix("Wuye") == "WUY"
    assert district_prefix("Wuye District") == "WUY"
    assert district_prefix("garki 2") == "GAR"


def test_prefix_rejects_short_names():
    with pytest.raises(ValueError):
        district_prefix("A1")


def test_full_hierarchy_format():
    street = street_code("WUY", 1)
    compound = compound_code(street, 1)
    building = building_code(compound, 1)
    premises = premises_code(building, 1)
    assert street == "WUY-ST-001"
    assert compound == "WUY-ST-001-C001"
    assert building == "WUY-ST-001-C001-B001"
    assert premises == "WUY-ST-001-C001-B001-P001"


def test_sequences_zero_pad_to_three():
    assert street_code("WUY", 42) == "WUY-ST-042"
    assert street_code("WUY", 999) == "WUY-ST-999"
