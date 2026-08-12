import io

from openpyxl import Workbook

from app.domain.route_analysis import parse


def _wb() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Estate Count"
    ws.append(["SN", "Estate", "Buildings", "Units", "Total"])
    ws.append([1, "Ivy Apartments", 13, 8, 104])
    ws.append([2, "Omako Estate", 1, 9, 9])
    ws.append([None, None, 2, 6, 12])          # continuation row
    ws.append([3, "423 Magnus Abe St", 1, 6, 6])
    ws.append([4, "Plot 386 Jaja Nwachukwu St", 6, 6, 36])
    st = wb.create_sheet("Street Count")
    st.append(["Street", "Length (Meters)"])
    st.append(["Ameh Ebute Street", 1855])
    st.append(["Alimoh Abu St", 118])
    st.append(["Alimoh Abu St", 118])          # duplicated in the real file
    st.append(["Unmeasured Road", None])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def test_streets_parsed_with_lengths():
    streets, _ = parse(_wb())
    names = [s.name for s in streets]
    assert "Ameh Ebute Street" in names
    assert next(s for s in streets if s.name == "Ameh Ebute Street").length_m == 1855


def test_duplicate_street_rows_collapse():
    streets, _ = parse(_wb())
    assert sum(1 for s in streets if s.name == "Alimoh Abu St") == 1


def test_street_without_a_length_is_kept():
    streets, _ = parse(_wb())
    assert next(s for s in streets if s.name == "Unmeasured Road").length_m is None


def test_continuation_rows_inherit_the_estate_name():
    _, estates = parse(_wb())
    omako = [e for e in estates if e.estate_name == "Omako Estate"]
    assert len(omako) == 2
    assert {e.units_per_building for e in omako} == {9, 6}


def test_typology_inferred_from_unit_count():
    _, estates = parse(_wb())
    ivy = next(e for e in estates if e.estate_name == "Ivy Apartments")
    assert ivy.typology == "block"      # 8 units


def test_street_hint_extracted_from_plot_labels():
    _, estates = parse(_wb())
    hints = {e.estate_name: e.street_hint for e in estates}
    assert hints["423 Magnus Abe St"] == "Magnus Abe St"
    assert hints["Plot 386 Jaja Nwachukwu St"] == "Jaja Nwachukwu St"
    assert hints["Ivy Apartments"] is None
