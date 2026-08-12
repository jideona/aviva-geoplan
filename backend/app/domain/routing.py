"""Underground route generation over the street graph.

Feeder (NOC to FDH) and distribution (FDH to FAT) routes follow streets, not
straight lines, because the plant is trenched along the carriageway or verge.
Routes are unioned into a tree so a duct shared by several FATs is trenched —
and costed — once, which is the difference between a drawing and a BOQ.

Pure graph work on shapely geometry in a metric CRS. No database, no pgRouting
dependency; a hand-rolled Dijkstra keeps it runnable against fixtures.
"""
import heapq
import math
from dataclasses import dataclass, field

from shapely.geometry import LineString, Point
from shapely.geometry.base import BaseGeometry

# Coincident endpoints within this many metres are treated as one node, so the
# graph actually connects where streets meet.
SNAP_TOLERANCE_M = 2.0


def _key(x: float, y: float) -> tuple[int, int]:
    return (round(x / SNAP_TOLERANCE_M), round(y / SNAP_TOLERANCE_M))


@dataclass
class RoadEdge:
    a: tuple[int, int]
    b: tuple[int, int]
    length: float
    geometry: LineString


class StreetGraph:
    """Undirected weighted graph of street segments."""

    def __init__(self) -> None:
        self.nodes: dict[tuple[int, int], tuple[float, float]] = {}
        self.adj: dict[tuple[int, int], list[tuple[tuple[int, int], float, LineString]]] = {}
        self._keys: list | None = None      # lazy nearest-node index
        self._coords = None                  # numpy array of node coords

    def add_road(self, line: LineString) -> None:
        coords = list(line.coords)
        for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
            ka, kb = _key(x1, y1), _key(x2, y2)
            if ka == kb:
                continue
            self.nodes.setdefault(ka, (x1, y1))
            self.nodes.setdefault(kb, (x2, y2))
            seg = LineString([(x1, y1), (x2, y2)])
            self.adj.setdefault(ka, []).append((kb, seg.length, seg))
            self.adj.setdefault(kb, []).append((ka, seg.length, seg))

    @classmethod
    def from_roads(cls, roads: list[BaseGeometry]) -> "StreetGraph":
        g = cls()
        for r in roads:
            parts = r.geoms if r.geom_type.startswith("Multi") else [r]
            for p in parts:
                if isinstance(p, LineString) and p.length > 0:
                    g.add_road(p)
        return g

    def nearest_node(self, point: Point) -> tuple[int, int]:
        if not self.nodes:
            raise RoutingError("The street graph is empty.")
        # Vectorised nearest lookup. Called once per building + FAT (thousands
        # of times for the drops layer); a Python loop over every node each time
        # dominated the runtime. numpy does the whole scan in C.
        if self._keys is None:
            import numpy as np
            self._keys = list(self.nodes.keys())
            self._coords = np.array([self.nodes[k] for k in self._keys],
                                    dtype=float)
        import numpy as np
        d = self._coords - (point.x, point.y)
        return self._keys[int(np.einsum("ij,ij->i", d, d).argmin())]

    def shortest_path(self, src: tuple[int, int], dst: tuple[int, int]):
        """Dijkstra. Returns (length, list of edge LineStrings)."""
        if src == dst:
            return 0.0, []
        dist = {src: 0.0}
        prev: dict = {}
        pq = [(0.0, src)]
        while pq:
            d, u = heapq.heappop(pq)
            if u == dst:
                break
            if d > dist.get(u, math.inf):
                continue
            for v, w, seg in self.adj.get(u, []):
                nd = d + w
                if nd < dist.get(v, math.inf):
                    dist[v] = nd
                    prev[v] = (u, seg)
                    heapq.heappush(pq, (nd, v))
        if dst not in dist:
            return math.inf, []
        edges = []
        node = dst
        while node != src:
            u, seg = prev[node]
            edges.append(seg)
            node = u
        return dist[dst], list(reversed(edges))

    def _path_nodes(self, src: tuple[int, int], dst: tuple[int, int]):
        """Dijkstra returning (length, ordered node coordinates) so a single
        continuous polyline can be assembled — segment orientation in the
        adjacency list is not travel-direction consistent, so we walk nodes."""
        if src == dst:
            return 0.0, [self.nodes[src]]
        dist = {src: 0.0}
        prev: dict = {}
        pq = [(0.0, src)]
        while pq:
            d, u = heapq.heappop(pq)
            if u == dst:
                break
            if d > dist.get(u, math.inf):
                continue
            for v, w, _seg in self.adj.get(u, []):
                nd = d + w
                if nd < dist.get(v, math.inf):
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(pq, (nd, v))
        if dst not in dist:
            return math.inf, []
        keys = [dst]
        while keys[-1] != src:
            keys.append(prev[keys[-1]])
        return dist[dst], [self.nodes[k] for k in reversed(keys)]

    def shortest_paths_from(self, source: tuple[int, int]):
        """Single-source Dijkstra: (dist, prev) over every reachable node, so a
        FAT's whole cluster of drops can be routed from ONE search instead of
        one search per building — the bulk path used for the drops layer."""
        dist = {source: 0.0}
        prev: dict = {}
        pq = [(0.0, source)]
        while pq:
            d, u = heapq.heappop(pq)
            if d > dist.get(u, math.inf):
                continue
            for v, w, _seg in self.adj.get(u, []):
                nd = d + w
                if nd < dist.get(v, math.inf):
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(pq, (nd, v))
        return dist, prev

    def route_via(self, a: Point, a_node: tuple[int, int], stub_a: float,
                  dist: dict, prev: dict, b: Point):
        """Assemble one drop from a precomputed single-source result (dist/prev
        from `shortest_paths_from(a_node)`, stub_a = a→a_node lateral). Returns
        (LineString, total_length_m) or (None, inf) if b is unreachable."""
        nb = self.nearest_node(b)
        if nb not in dist:
            return None, math.inf
        if nb == a_node:
            node_coords = [self.nodes[a_node]]
        else:
            keys = [nb]
            while keys[-1] != a_node:
                keys.append(prev[keys[-1]])
            node_coords = [self.nodes[k] for k in reversed(keys)]
        pts = [(a.x, a.y), *node_coords, (b.x, b.y)]
        clean = [pts[0]]
        for p in pts[1:]:
            if (p[0] - clean[-1][0]) ** 2 + (p[1] - clean[-1][1]) ** 2 > 1e-9:
                clean.append(p)
        if len(clean) < 2:
            return None, math.inf
        stub_b = b.distance(Point(self.nodes[nb]))
        return LineString(clean), dist[nb] + stub_a + stub_b

    def route_between(self, a: Point, b: Point):
        """Full routed drop from point a to point b: a lateral to a's nearest
        node, the shortest path along the network, then a lateral to b. Returns
        (LineString in graph CRS, total_length_m) or (None, inf) if unreachable.
        The network can be streets, service ways, footpaths or any traced
        corridor — whatever line features were fed to the graph."""
        na, nb = self.nearest_node(a), self.nearest_node(b)
        length, node_coords = self._path_nodes(na, nb)
        if not node_coords:
            return None, math.inf
        pts = [(a.x, a.y), *node_coords, (b.x, b.y)]
        clean = [pts[0]]
        for p in pts[1:]:
            if (p[0] - clean[-1][0]) ** 2 + (p[1] - clean[-1][1]) ** 2 > 1e-9:
                clean.append(p)
        stub_a = a.distance(Point(self.nodes[na]))
        stub_b = b.distance(Point(self.nodes[nb]))
        if len(clean) < 2:
            return None, math.inf
        return LineString(clean), length + stub_a + stub_b


class RoutingError(ValueError):
    """Message is safe to show the user."""


@dataclass
class RouteLeg:
    to_code: str
    length_m: float
    edges: list[LineString]


@dataclass
class DistributionTree:
    fdh_code: str
    legs: list[RouteLeg]
    trench_length_m: float             # unioned, shared duct counted once
    total_leg_length_m: float          # sum of legs, shared duct counted many
    unreachable: list[str] = field(default_factory=list)

    @property
    def sharing_saving_m(self) -> float:
        return round(self.total_leg_length_m - self.trench_length_m, 1)


def route_distribution(graph: StreetGraph, fdh: Point,
                       fats: list[tuple[str, Point]]) -> DistributionTree:
    """Route an FDH to each of its FATs, then union the ducts."""
    fdh_node = graph.nearest_node(fdh)
    legs: list[RouteLeg] = []
    unreachable: list[str] = []
    seen_edges: dict[int, float] = {}     # id(seg) -> length, for the union
    total = 0.0

    for code, pt in fats:
        node = graph.nearest_node(pt)
        length, edges = graph.shortest_path(fdh_node, node)
        if math.isinf(length):
            unreachable.append(code)
            continue
        legs.append(RouteLeg(code, round(length, 1), edges))
        total += length
        for seg in edges:
            seen_edges[id(seg)] = seg.length

    trench = sum(seen_edges.values())
    return DistributionTree(
        fdh_code="", legs=legs,
        trench_length_m=round(trench, 1),
        total_leg_length_m=round(total, 1),
        unreachable=unreachable)


def route_feeder(graph: StreetGraph, noc: Point,
                 fdhs: list[tuple[str, Point]]) -> list[RouteLeg]:
    """Feeder from the NOC to each FDH (radial)."""
    noc_node = graph.nearest_node(noc)
    out = []
    for code, pt in fdhs:
        length, edges = graph.shortest_path(noc_node, graph.nearest_node(pt))
        if math.isinf(length):
            continue
        out.append(RouteLeg(code, round(length, 1), edges))
    return out


# --- chamber (manhole / handhole) placement ---

@dataclass
class Chamber:
    kind: str            # "manhole" or "handhole"
    at: str              # what it serves
    x: float
    y: float


def chamber_schedule(noc: Point, fdhs: list[tuple[str, Point]],
                     fats: list[tuple[str, Point]],
                     trench_length_m: float,
                     manhole_spacing_m: float = 200.0) -> dict:
    """A handhole per FAT, a manhole per FDH and per feeder run interval."""
    handholes = len(fats)
    fdh_manholes = len(fdhs)
    run_manholes = int(trench_length_m // manhole_spacing_m)
    return {
        "handholes": handholes,
        "manholes": fdh_manholes + run_manholes,
        "manholes_at_fdh": fdh_manholes,
        "manholes_on_runs": run_manholes,
        "manhole_spacing_m": manhole_spacing_m,
    }
