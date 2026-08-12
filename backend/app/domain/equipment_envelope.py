"""Combined equipment envelope — what the full stock serves on one OLT.

The two stock sets are complementary, and — the correction that matters — both
phases draw PON ports from the *same* OLT. Phase 1 (connectorised, single-stage
1:32) consumes ports before Phase 2 (conventional two-stage) sees the rest.
Treating each phase as if it owned a full OLT overstates the total.
"""
import math
from dataclasses import dataclass


@dataclass
class Phase:
    name: str
    architecture: str
    premises: int
    pon_ports: int
    zero_purchase: bool
    purchase_needed: str
    splitters_used: dict
    note: str

    def as_dict(self) -> dict:
        return {"name": self.name, "architecture": self.architecture,
                "premises": self.premises, "pon_ports": self.pon_ports,
                "zero_purchase": self.zero_purchase,
                "purchase_needed": self.purchase_needed,
                "splitters_used": self.splitters_used, "note": self.note}


def envelope(splitter_stock: dict[int, int], connectorised_ports: int,
             connectorised_terminals: int, olt_pon_ports: int = 16) -> dict:
    stock = dict(splitter_stock)

    # Phase 1 — connectorised passive FATs, single-stage 1:32. Bounded by drop
    # ports, and it consumes PON ports at 32 premises per port.
    p1_premises = connectorised_ports
    p1_ports = math.ceil(p1_premises / 32) if p1_premises else 0
    p1_ports = min(p1_ports, olt_pon_ports)
    have_32 = stock.get(32, 0)
    p1_zero = p1_ports <= have_32

    phase1 = Phase(
        name="Phase 1 — connectorised core",
        architecture="single-stage 1:32, passive FAT",
        premises=p1_premises, pon_ports=p1_ports, zero_purchase=p1_zero,
        purchase_needed="none" if p1_zero else f"{p1_ports - have_32} x 1:32",
        splitters_used={32: p1_ports},
        note=f"{connectorised_terminals} pre-terminated FATs, "
             f"{connectorised_ports} ports. Fast, no splicing. Reach <= 350 m.")

    # Phase 2 — the PON ports Phase 1 left, built conventionally.
    remaining_ports = max(0, olt_pon_ports - p1_ports)
    have_8 = stock.get(8, 0)
    have_4 = stock.get(4, 0)

    if have_4 > 0:
        # Two-stage 1:32 (1:4 x 1:8): 1 primary + 4 secondary per port.
        ports = min(remaining_ports, have_4, have_8 // 4)
        p2_premises = ports * 32
        phase2 = Phase(
            name="Phase 2 — conventional 1:32",
            architecture="two-stage 1:4 x 1:8 = 1:32, spliced FAT",
            premises=p2_premises, pon_ports=ports, zero_purchase=False,
            purchase_needed=f"{ports} x 1:4 active (+ spares) plus conventional "
                            "FAT enclosures, bulk cable and closures",
            splitters_used={4: ports, 8: ports * 4},
            note="Comfortable optical budget (~17.5 dB); fills the OLT ports the "
                 "connectorised core did not use.")
        fallback = ("1:64 (1:8 x 1:8) needs no 1:4 but halves the optical "
                    "budget and uses more 1:8 per port. Not preferred with 1:4 "
                    "in stock.")
    else:
        # 1:64 fallback: 1 primary + 8 secondary per port.
        ports = min(remaining_ports, have_8 // 9)
        p2_premises = ports * 64
        phase2 = Phase(
            name="Phase 2 — conventional 1:64 (no 1:4)",
            architecture="two-stage 1:8 x 1:8 = 1:64, spliced FAT",
            premises=p2_premises, pon_ports=ports, zero_purchase=False,
            purchase_needed="conventional passive plant (splitters from stock)",
            splitters_used={8: ports * 9},
            note="Tight optical budget; verify the loss budget before building.")
        fallback = ("Procuring 1:4 converts this to two-stage 1:32: better "
                    "optical budget and fewer 1:8 per port.")

    used_4 = phase2.splitters_used.get(4, 0)
    used_8 = phase2.splitters_used.get(8, 0)

    return {
        "olt_pon_ports": olt_pon_ports,
        "phases": [phase1.as_dict(), phase2.as_dict()],
        "combined_premises": p1_premises + p2_premises,
        "pon_ports_used": p1_ports + phase2.pon_ports,
        "splitter_stock": splitter_stock,
        "splitters_remaining": {32: have_32 - p1_ports,
                                8: have_8 - used_8, 4: have_4 - used_4},
        "one_olt_ceiling": (p1_ports + phase2.pon_ports >= olt_pon_ports),
        "fallback": fallback,
        "note": (
            f"Both phases share one {olt_pon_ports}-port OLT: Phase 1 takes "
            f"{p1_ports} ports, Phase 2 the remaining {phase2.pon_ports}. "
            "Reaching beyond this needs a second OLT, not more splitters."
        ),
    }
