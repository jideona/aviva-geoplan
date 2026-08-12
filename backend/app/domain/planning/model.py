"""Planning engine inputs and outputs.

Plain data. The engine performs no I/O, so it can be run against fixtures and
benchmarked without a database (SAD 7.1).
"""
from dataclasses import dataclass, field

from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry


@dataclass(frozen=True)
class PlanningBuilding:
    id: str
    point: Point               # in the project metric CRS
    premises: int              # serviceable units
    premises_is_assumed: bool  # True where no survey or model supplied it
    code: str | None = None
    street_id: str | None = None
    # Estate/parcel this building belongs to. Buildings sharing a group are
    # kept together in whole FATs rather than fragmented across shared ones.
    group_id: str | None = None


@dataclass(frozen=True)
class PlanningRoad:
    id: str
    geometry: BaseGeometry     # in the project metric CRS
    road_class: str


@dataclass
class ServingZone:
    index: int
    fat_point: Point
    building_ids: list[str]
    premises: int
    max_drop_m: float
    avg_drop_m: float
    road_id: str | None
    road_offset_m: float | None
    warnings: list[str] = field(default_factory=list)

    @property
    def code_suffix(self) -> str:
        return f"FAT-{self.index:03d}"


@dataclass
class Fdh:
    index: int
    point: Point
    fat_codes: list[str]
    premises: int
    splitters: int
    splitter_ratio: int
    road_id: str | None
    road_offset_m: float | None
    max_distribution_m: float

    @property
    def code_suffix(self) -> str:
        return f"FDH-{self.index:02d}"

    @property
    def capacity(self) -> int:
        return self.splitters * self.splitter_ratio

    @property
    def utilisation_pct(self) -> float:
        return round(self.premises / self.capacity * 100, 1) if self.capacity else 0.0


@dataclass
class PlanningResult:
    zones: list[ServingZone]
    unassigned_building_ids: list[str]
    engine_version: str
    rules_applied: dict
    premises_total: int
    premises_assumed_count: int
    splitter_allocation: dict = field(default_factory=dict)
    fdhs: list["Fdh"] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        used = sum(z.premises for z in self.zones)
        drops = [z.max_drop_m for z in self.zones] or [0.0]
        return {
            "zones": len(self.zones),
            "buildings_served": sum(len(z.building_ids) for z in self.zones),
            "premises_served": used,
            "premises_total": self.premises_total,
            "unassigned_buildings": len(self.unassigned_building_ids),
            "max_drop_m": round(max(drops), 1),
            "avg_zone_premises": round(used / len(self.zones), 1) if self.zones else 0,
            "premises_assumed_count": self.premises_assumed_count,
            "engine_version": self.engine_version,
            "splitter_allocation": self.splitter_allocation,
            "fdh_count": len(self.fdhs),
            "fdh_capacity_each": (self.fdhs[0].capacity if self.fdhs else 0),
        }
