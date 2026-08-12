from shapely.geometry import LineString, Point

from app.domain.street_assignment import (AssignmentCandidate, AssignmentParams,
                                          assign, summarise)

# Coordinates are metres in a projected CRS, as the algorithm requires.
MAIN = AssignmentCandidate("main", "Ameh Ebute Street", 0, LineString([(0, 0), (200, 0)]))
LANE = AssignmentCandidate("lane", None, 5, LineString([(0, 40), (200, 40)]))
FAR = AssignmentCandidate("far", "Railway Road", 3, LineString([(0, 300), (200, 300)]))


def test_building_assigns_to_the_nearest_road():
    [p] = assign([("b1", Point(50, 10))], [MAIN, LANE, FAR])
    assert p.street_id == "main"
    assert p.distance_m == 10.0
    assert p.confidence > 0.6


def test_named_residential_beats_a_closer_unnamed_service_lane():
    # 22 m from the service lane, 30 m from the named street. The address is
    # the street, not the lane behind the compound.
    [p] = assign([("b1", Point(50, 18))], [MAIN, LANE])
    assert p.street_id == "main"


def test_unnamed_road_still_assigns_but_is_flagged_for_naming():
    [p] = assign([("b1", Point(50, 39))], [LANE])
    assert p.street_id == "lane"
    assert p.needs_field_name is True
    assert "needs a field name" in p.reason


def test_unnamed_assignment_carries_lower_confidence_than_named():
    [named] = assign([("b1", Point(50, 5))], [MAIN])
    [unnamed] = assign([("b2", Point(50, 45))], [LANE])
    assert unnamed.confidence < named.confidence


def test_building_beyond_max_distance_is_left_unassigned():
    [p] = assign([("b1", Point(50, 250))], [MAIN, LANE],
                 AssignmentParams(max_distance_m=60))
    assert p.street_id is None
    assert p.confidence == 0.0
    assert "no road within" in p.reason


def test_ambiguity_between_two_close_roads_lowers_confidence():
    equidistant = AssignmentCandidate("alt", "Other Street", 0,
                                      LineString([(0, 20), (200, 20)]))
    [p] = assign([("b1", Point(50, 10))], [MAIN, equidistant])
    assert p.confidence < 0.75
    assert "nearly as close" in p.reason


def test_no_streets_available_is_reported_not_crashed():
    [p] = assign([("b1", Point(0, 0))], [])
    assert p.street_id is None
    assert p.reason == "no streets available"


def test_summary_buckets_by_confidence():
    props = assign([("b1", Point(50, 2)), ("b2", Point(50, 45)),
                    ("b3", Point(50, 500))], [MAIN, LANE])
    s = summarise(props)
    assert s["total"] == 3
    assert s["unassigned"] == 1
    assert s["needs_field_name"] >= 1
