from shapely.geometry import LineString, Point

from app.domain.routing import (StreetGraph, chamber_schedule, route_distribution,
                                route_feeder)

# A simple grid: two horizontal + two vertical streets forming a ladder.
ROADS = [
    LineString([(0, 0), (100, 0), (200, 0)]),
    LineString([(0, 100), (100, 100), (200, 100)]),
    LineString([(0, 0), (0, 100)]),
    LineString([(100, 0), (100, 100)]),
    LineString([(200, 0), (200, 100)]),
]


def test_graph_connects_where_streets_meet():
    g = StreetGraph.from_roads(ROADS)
    # 6 distinct junctions on the ladder
    assert len(g.nodes) == 6


def test_shortest_path_follows_streets_not_straight_line():
    g = StreetGraph.from_roads(ROADS)
    src = g.nearest_node(Point(0, 0))
    dst = g.nearest_node(Point(200, 100))
    length, edges = g.shortest_path(src, dst)
    # Manhattan distance along the grid is 300, not the 224 straight line.
    assert length == 300
    assert edges


def test_distribution_tree_unions_shared_duct():
    # A trunk with two spurs off its far end; both FATs must use the trunk.
    roads = [LineString([(0, 0), (300, 0)]),        # trunk
             LineString([(300, 0), (300, 50)]),     # spur to F1
             LineString([(300, 0), (300, -50)])]    # spur to F2
    g = StreetGraph.from_roads(roads)
    tree = route_distribution(g, Point(0, 0),
                              [("F1", Point(300, 50)), ("F2", Point(300, -50))])
    # Legs: 350 + 350 = 700. Trench: 300 trunk + 50 + 50 = 400.
    assert tree.total_leg_length_m == 700
    assert tree.trench_length_m == 400
    assert tree.sharing_saving_m == 300


def test_an_unreachable_fat_is_reported_not_dropped():
    # Two disconnected street fragments: an FDH on one, a FAT on the other.
    roads = [LineString([(0, 0), (100, 0)]),
             LineString([(500, 500), (600, 500)])]
    g = StreetGraph.from_roads(roads)
    tree = route_distribution(g, Point(0, 0), [("F1", Point(600, 500))])
    assert "F1" in tree.unreachable
    assert not tree.legs


def test_feeder_routes_from_noc_to_each_fdh():
    g = StreetGraph.from_roads(ROADS)
    legs = route_feeder(g, Point(0, 0), [("FDH1", Point(200, 100))])
    assert legs and legs[0].length_m == 300


def test_chamber_schedule_places_handhole_per_fat_and_manhole_per_fdh():
    s = chamber_schedule(Point(0, 0), [("FDH1", Point(0, 0))],
                         [("F1", Point(1, 1)), ("F2", Point(2, 2))],
                         trench_length_m=850, manhole_spacing_m=200)
    assert s["handholes"] == 2
    assert s["manholes_at_fdh"] == 1
    assert s["manholes_on_runs"] == 4     # 850 // 200
