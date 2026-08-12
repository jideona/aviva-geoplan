"""Design rules for the fibre planning engine (SRD FR-ZON-001 to FR-ZON-007).

Every value is a decision an engineer should be able to see and change. None
are constants buried in the algorithm.
"""
from dataclasses import dataclass, field

# Standard splitter ratios. A FAT's usable capacity is its splitter ratio less
# the spare reserved for growth.
SPLITTER_RATIOS = (2, 4, 8, 16, 32, 64, 128)


@dataclass(frozen=True)
class DesignRules:
    # --- splitting architecture ---
    # Single-stage: the 1:32 splitter sits at the FDH; the FAT is a passive drop
    # terminal. Chosen to deploy from existing 1:32 stock without buying the
    # 1:4 primaries a two-stage cascade would need.
    split_stage: str = "single"          # "single" or "two"
    fdh_split_ratio: int = 32            # the split, at the FDH in single-stage
    fat_split_ratio: int = 1            # 1 = passive FAT (no split at the FAT)

    # A passive FAT is sized by its physical drop-port count, not by a splitter
    # ratio. 16 is a common sealed handhole terminal; 8/12/24 also exist.
    fat_port_count: int = 16

    # In two-stage mode the FAT carries this splitter instead.
    fat_splitter_ratio: int = 16

    spare_port_ratio: float = 0.20       # reserve for future connections
    max_drop_length_m: float = 150.0     # cable from FAT to premises
    min_premises_per_fat: int = 4        # below this, merge into a neighbour

    # --- FDH tier ---
    # Splitters per FDH cabinet. 3 x 1:32 = 96 premises per FDH, and 6 such
    # FDHs consume the full 18-splitter stock (the pilot unit).
    splitters_per_fdh: int = 3
    max_fdh_distribution_m: float = 2000.0   # FDH-to-FAT distribution reach

    # Anchor FDH clustering to the head-end so the first cabinets land near the
    # NOC — essential for a connectorised pilot whose feeder cannot run far.
    noc_anchor: tuple | None = None          # (metric_x, metric_y) or None

    # Splitter stock. 1:4 procured (20) to enable two-stage 1:32 (1:4 x 1:8) on
    # the conventional build — a trivial spend that keeps the optical budget
    # comfortable and uses all OLT PON ports, rather than the 1:64 workaround
    # that idles half the OLT.
    splitter_stock: tuple = ((32, 18), (8, 78), (4, 20))

    # --- premises assumption ---
    # Where a building has no surveyed or modelled premises count, this value
    # is used AND the zone is flagged. It is deliberately 1, so an unclassified
    # register under-states rather than over-states capacity.
    assumed_premises_per_building: int = 1

    # --- placement ---
    max_fat_road_offset_m: float = 25.0  # a FAT must be reachable from a road
    prefer_road_classes: tuple[str, ...] = (
        "residential", "unclassified", "tertiary", "living_street")

    # --- determinism ---
    # Ties are broken by identifier rather than iteration order so that two
    # runs over the same input produce identical designs (SRD FR-RTE-011).
    engine_version: str = "0.1.0"

    warnings: tuple[str, ...] = field(default=())

    @property
    def usable_ports(self) -> int:
        """Premises one FAT can serve.

        Passive FAT: bounded by physical drop ports. Two-stage FAT: bounded by
        its secondary splitter. Spare is reserved from whichever applies.
        """
        base = (self.fat_port_count if self.split_stage == "single"
                else self.fat_splitter_ratio)
        return max(1, int(base * (1 - self.spare_port_ratio)))

    @property
    def overall_split(self) -> int:
        if self.split_stage == "single":
            return self.fdh_split_ratio
        return self.fdh_split_ratio * self.fat_split_ratio

    @property
    def stock_map(self) -> dict:
        return {int(r): int(q) for r, q in self.splitter_stock}

    @property
    def fdh_premises_capacity(self) -> int:
        """Premises one FDH serves: splitters x split ratio."""
        return self.splitters_per_fdh * self.fdh_split_ratio

    def validate(self) -> list[str]:
        errors = []
        if self.split_stage not in ("single", "two"):
            errors.append("split_stage must be 'single' or 'two'.")
        if self.fdh_split_ratio not in SPLITTER_RATIOS:
            errors.append(
                f"FDH split ratio {self.fdh_split_ratio} is not standard "
                f"{SPLITTER_RATIOS}.")
        if self.split_stage == "two" and self.fat_split_ratio not in SPLITTER_RATIOS:
            errors.append(
                f"FAT split ratio {self.fat_split_ratio} is not standard.")
        if self.split_stage == "single" and self.fat_port_count < 1:
            errors.append("A passive FAT needs at least one drop port.")
        if not 0.0 <= self.spare_port_ratio < 0.9:
            errors.append("Spare port ratio must be between 0 and 0.9.")
        if self.max_drop_length_m <= 0:
            errors.append("Maximum drop length must be positive.")
        return errors
