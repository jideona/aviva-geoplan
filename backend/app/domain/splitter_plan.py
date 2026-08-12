"""Splitter architecture planning against real stock (SRD FR-NET-004).

The point of this module is to make the trade-off explicit: a requested split
architecture is checked against inventory, and where it cannot be met from
stock, the shortfall is reported rather than a purchase quietly assumed.
"""
from dataclasses import dataclass, field
from enum import Enum

VALID_RATIOS = (2, 4, 8, 16, 32, 64, 128)


class SplitStage(str, Enum):
    SINGLE = "single"   # one splitter, at the FDH; FATs are passive splice points
    TWO = "two"         # primary at FDH, secondary at FAT


@dataclass(frozen=True)
class SplitArchitecture:
    stage: SplitStage
    fdh_ratio: int              # primary (or the only) split
    fat_ratio: int              # secondary; 1 for single-stage

    @property
    def overall(self) -> int:
        return self.fdh_ratio * self.fat_ratio

    def describe(self) -> str:
        if self.stage is SplitStage.SINGLE:
            return f"single-stage 1:{self.fdh_ratio} at the FDH, FAT passive"
        return f"1:{self.fdh_ratio} at FDH x 1:{self.fat_ratio} at FAT = 1:{self.overall}"


@dataclass
class SplitterDemand:
    """Splitters required to serve a set of PON ports at a target split."""
    fdh_ratio: int
    fdh_count: int
    fat_ratio: int
    fat_count: int


@dataclass
class InventoryLine:
    ratio: int
    in_stock: int
    required: int

    @property
    def gap(self) -> int:
        return max(0, self.required - self.in_stock)

    @property
    def surplus(self) -> int:
        return max(0, self.in_stock - self.required)


@dataclass
class SplitterPlan:
    architecture: SplitArchitecture
    pon_ports: int
    endpoints: int
    lines: list[InventoryLine]
    zero_purchase: bool
    warnings: list[str] = field(default_factory=list)

    def to_purchase(self) -> list[InventoryLine]:
        return [l for l in self.lines if l.gap > 0]


def demand_for(arch: SplitArchitecture, pon_ports: int,
               spare_ratio: float = 0.25) -> SplitterDemand:
    """How many splitters an architecture needs to light `pon_ports`.

    One primary splitter per PON port; one secondary per primary output leg.
    Spare is added on top as whole units.
    """
    def with_spare(n: int) -> int:
        return n + max(1, round(n * spare_ratio)) if n else 0

    if arch.stage is SplitStage.SINGLE:
        return SplitterDemand(arch.fdh_ratio, with_spare(pon_ports), 1, 0)

    primaries = pon_ports
    secondaries = pon_ports * arch.fdh_ratio      # one FAT splitter per primary leg
    return SplitterDemand(arch.fdh_ratio, with_spare(primaries),
                          arch.fat_ratio, with_spare(secondaries))


def plan(arch: SplitArchitecture, pon_ports: int, stock: dict[int, int],
         spare_ratio: float = 0.25) -> SplitterPlan:
    demand = demand_for(arch, pon_ports, spare_ratio)
    lines: list[InventoryLine] = []

    need: dict[int, int] = {}
    need[demand.fdh_ratio] = need.get(demand.fdh_ratio, 0) + demand.fdh_count
    if arch.stage is SplitStage.TWO:
        need[demand.fat_ratio] = need.get(demand.fat_ratio, 0) + demand.fat_count

    for ratio, required in sorted(need.items()):
        lines.append(InventoryLine(ratio=ratio, in_stock=stock.get(ratio, 0),
                                   required=required))

    zero_purchase = all(l.gap == 0 for l in lines)
    warnings: list[str] = []
    if not zero_purchase:
        gaps = ", ".join(f"{l.gap}x 1:{l.ratio}" for l in lines if l.gap)
        warnings.append(
            f"{arch.describe()} cannot be met from stock. Shortfall: {gaps}.")

    return SplitterPlan(
        architecture=arch, pon_ports=pon_ports,
        endpoints=pon_ports * arch.overall, lines=lines,
        zero_purchase=zero_purchase, warnings=warnings)


def options(pon_ports: int, stock: dict[int, int],
            spare_ratio: float = 0.25) -> list[SplitterPlan]:
    """Enumerate architectures for the port count, so zero-purchase paths and
    their trade-offs can be compared side by side."""
    candidates = [
        SplitArchitecture(SplitStage.SINGLE, 32, 1),
        SplitArchitecture(SplitStage.TWO, 4, 8),
        SplitArchitecture(SplitStage.TWO, 8, 4),
        SplitArchitecture(SplitStage.TWO, 8, 8),   # 1:64
        SplitArchitecture(SplitStage.SINGLE, 16, 1),
    ]
    return [plan(a, pon_ports, stock, spare_ratio) for a in candidates]
