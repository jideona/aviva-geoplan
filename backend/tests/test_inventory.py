from app.services.inventory_service import (
    _bucket_for_som_item, _derive_match_key, parse_stock_rows)

CSV_HEADER = ("Stock Code,Asset Category,Subcategory,Manufacturer,"
             "Product / Asset Name,Model,Quantity Held,UoM,Condition\n")


def _csv(*rows: str) -> bytes:
    return (CSV_HEADER + "\n".join(rows)).encode()


def test_parses_basic_csv_rows():
    data = _csv(
        "AVN-CPE-001,Active Equipment,GPON ONT,TP-Link,TP-Link GPON ONT,AC1200,10,pcs,New",
        "AVN-ODN-001,Passive ODN,FDP,Excel,Excel Encasa 16F FDP,916-005,9,pcs,New",
    )
    rows, unmatched = parse_stock_rows("stock.csv", data)
    assert not unmatched
    assert len(rows) == 2
    assert rows[0]["stock_code"] == "AVN-CPE-001"
    assert rows[0]["quantity"] == 10.0
    assert rows[1]["product_name"] == "Excel Encasa 16F FDP"


def test_header_aliases_are_recognised_case_insensitively():
    data = ("SKU,Category,Item,Qty,Unit\n"
           "X-1,Splitters,1:32 PLC splitter,50,pcs\n").encode()
    rows, unmatched = parse_stock_rows("stock.csv", data)
    assert not unmatched
    assert rows[0]["stock_code"] == "X-1"
    assert rows[0]["category"] == "Splitters"
    assert rows[0]["quantity"] == 50.0


def test_blank_and_title_rows_are_skipped():
    # A title row and a totally blank row before the real header, like the
    # real Aviva Asset Register sheet has.
    data = ("Aviva Networx Asset Register\n\n"
           "Stock Code,Asset Category,Product / Asset Name,Quantity Held,UoM\n"
           "AVN-1,Active Equipment,Some ONT,5,pcs\n").encode()
    rows, _ = parse_stock_rows("stock.csv", data)
    assert len(rows) == 1
    assert rows[0]["product_name"] == "Some ONT"


def test_unmatched_columns_are_reported_not_dropped_silently():
    data = ("Stock Code,Asset Category,Product / Asset Name,Quantity Held,UoM,Weird Column\n"
           "AVN-1,Active Equipment,Some ONT,5,pcs,???\n").encode()
    rows, unmatched = parse_stock_rows("stock.csv", data)
    assert unmatched == ["Weird Column"]
    assert len(rows) == 1


def test_no_recognisable_header_raises():
    import pytest
    from app.services.inventory_service import InventoryError
    data = "a,b,c\n1,2,3\n".encode()
    with pytest.raises(InventoryError):
        parse_stock_rows("stock.csv", data)


# ---- match_key classification ------------------------------------------- #

def test_splitter_ratio_is_classified():
    key, attrs = _derive_match_key("Passive ODN", "Splitter", "1:32 PLC splitter", "")
    assert key == "splitter:32"
    assert attrs == {"ratio": 32}


def test_splitter_with_x_notation_is_classified():
    key, attrs = _derive_match_key("", "", "PLC splitter 1x8", "")
    assert key == "splitter:8"


def test_non_standard_ratio_is_not_classified_as_a_splitter():
    # 1:13 isn't a real PON splitter ratio — must not silently corrupt the
    # design engine's splitter stock figures.
    key, attrs = _derive_match_key("Splitter", "", "1:13 splitter", "")
    assert key is None


def test_connectorised_cable_kind_and_length_classified():
    key, attrs = _derive_match_key(
        "Passive ODN", "Drop assembly",
        "8way pre-terminated connectorised cable 250m", "")
    assert key == "connectorised_cable:8way:250"
    assert attrs == {"kind": "8way", "ports": 8, "length_m": 250}


def test_fibre_cable_drum_classified_by_count():
    key, attrs = _derive_match_key(
        "Cable", "Feeder", "96F fibre optic cable drum", "")
    assert key == "cable_drum:96"
    assert attrs == {"fibre_count": 96}


def test_fibre_pigtail_is_not_classified_as_a_cable_drum():
    # A pigtail mentions "fibre" but isn't bulk cable — must not pollute the
    # cable-drum stock figures.
    key, attrs = _derive_match_key("", "", "SC/APC pigtail 12F breakout", "")
    assert key is None


def test_microduct_size_classified():
    key, attrs = _derive_match_key(
        "Installation Hardware", "Duct", "Microduct 12/10mm", "")
    assert key == "microduct:12mm"
    assert attrs == {"diameter_mm": 12}


def test_unrelated_item_gets_no_match_key():
    key, attrs = _derive_match_key(
        "Installation Hardware", "Mounting bracket",
        "Hexatronic black mounting bracket", "")
    assert key is None
    assert attrs == {}


# ---- generic SOM bucket lookup ------------------------------------------ #

def test_som_item_names_map_to_expected_buckets():
    assert _bucket_for_som_item("16-port XGS-PON OLT") == "olt"
    assert _bucket_for_som_item("FDH splice closure") == "splice closure"
    assert _bucket_for_som_item("Handhole (at FAT)") == "handhole"
    assert _bucket_for_som_item("Manhole (at FDH)") == "manhole"
    assert _bucket_for_som_item("HDPE duct") == "hdpe duct"


def test_som_item_with_no_bucket_returns_none():
    assert _bucket_for_som_item("Some completely novel line item") is None
