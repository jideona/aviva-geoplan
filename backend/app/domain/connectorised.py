"""Fitting a design to pre-connectorised underground FTTP stock.

These cables are plug-and-play: fixed length, fixed way-count, factory
terminated. You cannot cut them. So the design is not "measure the route, buy
the cable" — it is "which fixed assets fit which routes", a constrained
assignment where a cable serves a FAT only if its length reaches and its ports
suffice.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CableSpec:
    kind: str            # "4way", "8way", "12way", "novux_12pt"
    ports: int           # drop ports (0 for a fibre feeder)
    length_m: int
    is_feeder: bool = False


@dataclass
class StockItem:
    spec: CableSpec
    quantity: int


@dataclass
class DemandPoint:
    """A FAT position needing a connectorised terminal."""
    fat_code: str
    route_distance_m: float   # feed point to FAT, along the duct
    premises: int


@dataclass
class Assignment:
    fat_code: str
    route_distance_m: float
    premises: int
    cable: CableSpec
    slack_m: float           # spare reach
    spare_ports: int


@dataclass
class Unserved:
    fat_code: str
    route_distance_m: float
    premises: int
    reason: str


@dataclass
class FitResult:
    assignments: list[Assignment]
    unserved: list[Unserved]
    leftover: list[StockItem] = field(default_factory=list)

    @property
    def premises_served(self) -> int:
        return sum(a.premises for a in self.assignments)

    def summary(self) -> dict:
        used = {}
        for a in self.assignments:
            used[a.cable.kind] = used.get(a.cable.kind, 0) + 1
        return {
            "fats_served": len(self.assignments),
            "fats_unserved": len(self.unserved),
            "premises_served": self.premises_served,
            "premises_unserved": sum(u.premises for u in self.unserved),
            "cables_used": used,
            "cables_leftover": {i.spec.kind + f"_{i.spec.length_m}m": i.quantity
                                for i in self.leftover if i.quantity},
            "total_slack_m": round(sum(a.slack_m for a in self.assignments), 1),
            "total_spare_ports": sum(a.spare_ports for a in self.assignments),
        }


def stock_from_lines(lines: list[tuple[str, int, int, int]]) -> list[StockItem]:
    """lines: (kind, ports, length_m, quantity)."""
    out = []
    for kind, ports, length, qty in lines:
        out.append(StockItem(
            spec=CableSpec(kind=kind, ports=ports, length_m=length,
                           is_feeder=(ports == 0)),
            quantity=qty))
    return out


def fit(demand: list[DemandPoint], stock: list[StockItem]) -> FitResult:
    """Assign connectorised FAT cables to demand points.

    Strategy: serve the hardest demand first (farthest, then most premises),
    and for each use the *tightest* cable that fits — smallest port count that
    covers the premises, shortest length that reaches — so long and
    high-capacity cables are preserved for demand that needs them.
    """
    # Expand FAT terminals (non-feeder) into an available pool.
    pool: list[CableSpec] = []
    feeders: list[StockItem] = []
    for item in stock:
        if item.spec.is_feeder:
            feeders.append(StockItem(item.spec, item.quantity))
            continue
        pool.extend([item.spec] * item.quantity)

    order = sorted(demand, key=lambda d: (-d.route_distance_m, -d.premises))
    assignments: list[Assignment] = []
    unserved: list[Unserved] = []

    for d in order:
        # Candidates: reach the distance and cover the premises.
        candidates = [c for c in pool
                      if c.length_m >= d.route_distance_m and c.ports >= d.premises]
        if not candidates:
            # Explain the binding failure.
            reach = [c for c in pool if c.length_m >= d.route_distance_m]
            if not reach:
                reason = (f"no cable reaches {d.route_distance_m:.0f} m "
                          f"(longest left {max((c.length_m for c in pool), default=0)} m)")
            else:
                reason = (f"reachable cables cannot carry {d.premises} premises "
                          f"(best {max(c.ports for c in reach)} ports)")
            unserved.append(Unserved(d.fat_code, round(d.route_distance_m, 1),
                                     d.premises, reason))
            continue
        # Tightest fit: fewest ports, then least slack length.
        best = min(candidates, key=lambda c: (c.ports, c.length_m))
        pool.remove(best)
        assignments.append(Assignment(
            fat_code=d.fat_code, route_distance_m=round(d.route_distance_m, 1),
            premises=d.premises, cable=best,
            slack_m=round(best.length_m - d.route_distance_m, 1),
            spare_ports=best.ports - d.premises))

    # Whatever is left in the pool, recompacted by spec.
    leftover: dict[tuple, int] = {}
    for c in pool:
        leftover[(c.kind, c.ports, c.length_m)] = \
            leftover.get((c.kind, c.ports, c.length_m), 0) + 1
    left_items = [StockItem(CableSpec(k, p, l), q)
                  for (k, p, l), q in leftover.items()]
    left_items.extend(feeders)

    return FitResult(assignments=assignments, unserved=unserved,
                     leftover=left_items)
