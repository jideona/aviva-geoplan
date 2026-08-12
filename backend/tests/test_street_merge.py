"""Segment merging is a data-model question, tested at the domain level.

OSM splits a way at every junction, bridge and surface change. Naming two
segments identically means they are one street, and the register should say so
— 437 segments is not 437 streets.
"""
from shapely.geometry import LineString, MultiLineString
from shapely.ops import linemerge, unary_union

from app.domain.name_matching import merge_key


def test_abbreviated_suffixes_merge_to_one_key():
    variants = ["Ameh Ebute Street", "Ameh Ebute St", "ameh ebute street",
                "AMEH EBUTE STR"]
    assert len({merge_key(v) for v in variants}) == 1


def test_different_road_types_do_not_merge():
    # Same name, genuinely different roads. Dropping the suffix would join them.
    assert merge_key("Ameh Ebute Street") != merge_key("Ameh Ebute Close")
    assert merge_key("Reuben Okoya Crescent") != merge_key("Reuben Okoya Road")


def test_crescent_abbreviations_merge():
    assert merge_key("Ken Nnamani Cres") == merge_key("Ken Nnamani Crescent")


def test_blank_or_suffix_only_names_yield_no_key():
    assert merge_key("") == ""
    assert merge_key("   ") == ""


def test_touching_segments_merge_into_a_single_line():
    a = LineString([(0, 0), (100, 0)])
    b = LineString([(100, 0), (250, 0)])
    merged = linemerge(unary_union([a, b]))
    assert merged.geom_type == "LineString"
    assert merged.length == 250


def test_disjoint_segments_of_one_street_stay_multipart():
    # A street interrupted by a roundabout is still one street.
    a = LineString([(0, 0), (100, 0)])
    b = LineString([(140, 0), (250, 0)])
    merged = linemerge(unary_union([a, b]))
    if merged.geom_type == "LineString":
        merged = MultiLineString([merged])
    assert merged.geom_type == "MultiLineString"
    assert round(merged.length) == 210


def test_merged_length_is_the_sum_not_the_longest():
    parts = [LineString([(0, 0), (100, 0)]),
             LineString([(100, 0), (180, 0)]),
             LineString([(180, 0), (300, 0)])]
    merged = linemerge(unary_union(parts))
    assert merged.length == 300
