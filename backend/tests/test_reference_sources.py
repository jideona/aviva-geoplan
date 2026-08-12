import pytest

from app.domain.reference_sources import RingAssemblyError, assemble_rings, normalize_name


def test_normalize_strips_case_and_whitespace():
    assert normalize_name("Wuye") == "wuye"
    assert normalize_name("WUYE  ") == "wuye"
    assert normalize_name("  wuye") == "wuye"


def test_normalize_strips_administrative_suffixes():
    assert normalize_name("Wuye District") == "wuye"
    assert normalize_name("Central Abaji Ward") == "central abaji"


def test_normalize_keeps_ordinal_and_numeric_suffixes():
    # These distinguish genuinely different districts, not the same one.
    assert normalize_name("Wuse II") == "wuse ii"
    assert normalize_name("Garki 2") == "garki 2"
    assert normalize_name("Garki 2") != normalize_name("Garki")


def test_normalize_strips_punctuation():
    assert normalize_name("Utako-Suburb") == "utako suburb"
    assert normalize_name("Utako, Suburb") == "utako suburb"


def test_normalize_matches_across_source_variants():
    # A GRID3 wardname and an OSM relation name for the same place, in the
    # differing styles each source actually uses.
    assert normalize_name("Wuye District") == normalize_name("wuye")


# A unit square, one segment per side, used across the ring-assembly tests.
_A = [(0.0, 0.0), (1.0, 0.0)]
_B = [(1.0, 0.0), (1.0, 1.0)]
_C = [(1.0, 1.0), (0.0, 1.0)]
_D = [(0.0, 1.0), (0.0, 0.0)]


def test_assemble_rings_in_order():
    rings = assemble_rings([_A, _B, _C, _D])
    assert len(rings) == 1
    ring = rings[0]
    assert ring[0] == ring[-1]
    assert set(ring) == {(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)}


def test_assemble_rings_handles_reversed_segment():
    d_reversed = list(reversed(_D))  # [(0,0), (0,1)] instead of [(0,1), (0,0)]
    rings = assemble_rings([_A, _B, _C, d_reversed])
    assert len(rings) == 1
    ring = rings[0]
    assert ring[0] == ring[-1]
    assert set(ring) == {(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)}


def test_assemble_rings_handles_out_of_order_segments():
    rings = assemble_rings([_C, _A, _D, _B])
    assert len(rings) == 1
    assert rings[0][0] == rings[0][-1]


def test_assemble_rings_produces_multiple_disjoint_rings():
    # A second, unrelated square (an exclave) mixed in with the first.
    e = [(10.0, 10.0), (11.0, 10.0)]
    f = [(11.0, 10.0), (11.0, 11.0)]
    g = [(11.0, 11.0), (10.0, 11.0)]
    h = [(10.0, 11.0), (10.0, 10.0)]

    rings = assemble_rings([_A, e, _B, f, _C, g, _D, h])
    assert len(rings) == 2
    for ring in rings:
        assert ring[0] == ring[-1]
    coord_sets = [set(r) for r in rings]
    assert {(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)} in coord_sets
    assert {(10.0, 10.0), (11.0, 10.0), (11.0, 11.0), (10.0, 11.0)} in coord_sets


def test_assemble_rings_raises_on_a_ring_that_cannot_close():
    # An open chain with no segment left to close it back to its start.
    with pytest.raises(RingAssemblyError):
        assemble_rings([[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]])


def test_assemble_rings_raises_when_a_gap_leaves_segments_stranded():
    # B is missing, so the chain can never reach back to (1, 0) then (0, 0).
    with pytest.raises(RingAssemblyError):
        assemble_rings([_A, _C, _D])
