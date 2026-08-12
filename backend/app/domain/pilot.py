"""Assemble a buildable pilot from a design, bounded by OLT ports and stock.

Two phases sharing one OLT: a fast connectorised core near the head-end, then a
conventional two-stage extension filling the remaining PON ports. The output is
an equipment schedule an engineer can hand to procurement and construction.
"""
import math
from dataclasses import dataclass, field


@dataclass
class PilotFat:
    fat_code: str
    phase: int
    premises: int
    route_m: float
    cable: str | None        # connectorised assembly, phase 1 only
    fat_type: str            # "connectorised" or "conventional"


@dataclass
class PilotPlan:
    olt_pon_ports: int
    phase1_fats: list[PilotFat]
    phase2_fats: list[PilotFat]
    unserved_fats: int
    equipment: dict
    warnings: list[str] = field(default_factory=list)

    @property
    def phase1_premises(self) -> int:
        return sum(f.premises for f in self.phase1_fats)

    @property
    def phase2_premises(self) -> int:
        return sum(f.premises for f in self.phase2_fats)

    @property
    def total_premises(self) -> int:
        return self.phase1_premises + self.phase2_premises


@dataclass
class FatDemand:
    fat_code: str
    distance_from_noc_m: float   # route, not straight-line
    premises: int


def build_pilot(demand: list[FatDemand], splitter_stock: dict[int, int],
                connectorised_fit, olt_pon_ports: int = 16) -> PilotPlan:
    """demand: FATs ordered arbitrarily; we sort by distance from the NOC.

    connectorised_fit: a FitResult from app.domain.connectorised, already run
    against the near-NOC demand.
    """
    ordered = sorted(demand, key=lambda d: d.distance_from_noc_m)

    # Phase 1: whatever the connectorised fit could place.
    assigned = {a.fat_code: a for a in connectorised_fit.assignments}
    phase1: list[PilotFat] = []
    p1_ports_used = 0
    for d in ordered:
        a = assigned.get(d.fat_code)
        if a is None:
            continue
        phase1.append(PilotFat(
            fat_code=d.fat_code, phase=1, premises=d.premises,
            route_m=round(d.distance_from_noc_m, 1),
            cable=f"{a.cable.kind} {a.cable.length_m}m", fat_type="connectorised"))
    p1_premises = sum(f.premises for f in phase1)
    p1_ports_used = math.ceil(p1_premises / 32) if p1_premises else 0

    # Phase 2: remaining PON ports, conventional two-stage 1:32.
    remaining_ports = max(0, olt_pon_ports - p1_ports_used)
    p2_capacity = remaining_ports * 32
    phase2: list[PilotFat] = []
    p2_premises = 0
    in_phase1 = {f.fat_code for f in phase1}
    for d in ordered:
        if d.fat_code in in_phase1:
            continue
        if p2_premises + d.premises > p2_capacity:
            continue
        phase2.append(PilotFat(
            fat_code=d.fat_code, phase=2, premises=d.premises,
            route_m=round(d.distance_from_noc_m, 1), cable=None,
            fat_type="conventional"))
        p2_premises += d.premises

    served = {f.fat_code for f in phase1} | {f.fat_code for f in phase2}
    unserved = sum(1 for d in demand if d.fat_code not in served)

    equipment = _equipment_schedule(phase1, phase2, splitter_stock, olt_pon_ports)
    warnings = []
    if p1_ports_used + remaining_ports >= olt_pon_ports:
        warnings.append(
            f"The {olt_pon_ports}-port OLT is full. Beyond this pilot a second "
            "OLT is required, not more splitters.")
    return PilotPlan(olt_pon_ports=olt_pon_ports, phase1_fats=phase1,
                     phase2_fats=phase2, unserved_fats=unserved,
                     equipment=equipment, warnings=warnings)


def _equipment_schedule(phase1, phase2, stock, olt_ports) -> dict:
    p1_premises = sum(f.premises for f in phase1)
    p2_premises = sum(f.premises for f in phase2)
    p1_ports = math.ceil(p1_premises / 32) if p1_premises else 0
    p2_ports = math.ceil(p2_premises / 32) if p2_premises else 0

    # Splitters
    splitter_1_32_p1 = p1_ports                    # single-stage at FDH
    splitter_1_4_p2 = p2_ports                     # primary
    splitter_1_8_p2 = p2_ports * 4                 # secondary
    spare = 0.25

    def line(ratio, need, role):
        have = stock.get(ratio, 0)
        buy = max(0, math.ceil(need * (1 + spare)) - have)
        return {"item": f"1:{ratio} splitter", "role": role,
                "required": need, "with_spares": math.ceil(need * (1 + spare)),
                "in_stock": have, "buy": buy}

    # Connectorised cables used
    conn = {}
    for f in phase1:
        conn[f.cable] = conn.get(f.cable, 0) + 1

    return {
        "olt": {"item": "16-port OLT", "required": 1, "ports_used": p1_ports + p2_ports,
                "note": "Single OLT fills at this pilot; growth needs a second."},
        "splitters": [
            line(32, splitter_1_32_p1, "Phase 1 single-stage at FDH"),
            line(4, splitter_1_4_p2, "Phase 2 primary at FDH"),
            line(8, splitter_1_8_p2, "Phase 2 secondary at FAT"),
        ],
        "connectorised_cables_used": conn,
        "fats": {"connectorised": len(phase1), "conventional": len(phase2),
                 "total": len(phase1) + len(phase2)},
        "conventional_plant": {
            "fat_enclosures": len(phase2),
            "note": "Bulk distribution cable and splice closures sized from "
                    "route lengths once street routing is run.",
        },
    }
