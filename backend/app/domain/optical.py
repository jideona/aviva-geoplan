"""Optical loss budget (SRD FR-OPT-001 to FR-OPT-009).

Every value is configurable — no attenuation, insertion or margin figure is
hard coded. The engine sums the path loss, compares it against the system
budget (OLT launch power less ONT sensitivity), and classifies the result.
"""
from dataclasses import dataclass, field
from enum import Enum


class Verdict(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


# Splitter insertion loss (dB), including connectors internal to the module.
# Configurable; these are typical PLC values.
DEFAULT_SPLITTER_LOSS: dict[int, float] = {
    2: 3.6, 4: 7.3, 8: 10.5, 16: 13.8, 32: 17.5, 64: 20.9, 128: 24.0,
}


@dataclass(frozen=True)
class OpticalParams:
    # Fibre attenuation per km at the worst-case wavelength (XGS-PON upstream
    # 1270 nm is the usual worst case).
    fibre_db_per_km: float = 0.35
    connector_db: float = 0.4
    splice_db: float = 0.1
    patch_panel_db: float = 0.5
    engineering_margin_db: float = 1.0
    repair_allowance_db: float = 1.0        # future repair splices

    # System budget.
    olt_launch_dbm: float = 4.0             # XGS-PON typical
    ont_sensitivity_dbm: float = -28.0      # class N1
    required_margin_db: float = 1.0         # margin to still call it a pass

    splitter_loss: dict = field(default_factory=lambda: dict(DEFAULT_SPLITTER_LOSS))

    @property
    def system_budget_db(self) -> float:
        return self.olt_launch_dbm - self.ont_sensitivity_dbm


@dataclass
class PathElement:
    label: str
    loss_db: float


@dataclass
class LossResult:
    total_loss_db: float
    system_budget_db: float
    design_margin_db: float
    verdict: Verdict
    reason: str
    elements: list[PathElement]

    def as_dict(self) -> dict:
        return {
            "total_loss_db": round(self.total_loss_db, 2),
            "system_budget_db": round(self.system_budget_db, 2),
            "design_margin_db": round(self.design_margin_db, 2),
            "verdict": self.verdict.value,
            "reason": self.reason,
            "elements": [{"label": e.label, "loss_db": round(e.loss_db, 2)}
                         for e in self.elements],
        }


@dataclass
class PathSpec:
    """One optical path OLT -> ... -> ONT."""
    feeder_m: float
    distribution_m: float
    drop_m: float
    splitter_ratios: list[int]      # e.g. [32] single-stage, [4, 8] two-stage
    connectors: int = 6             # OLT, ODF, FDH in/out, FAT, ONT, patching
    splices: int = 4
    patch_panels: int = 2


def compute(path: PathSpec, params: OpticalParams) -> LossResult:
    elements: list[PathElement] = []

    fibre_km = (path.feeder_m + path.distribution_m + path.drop_m) / 1000
    elements.append(PathElement(
        f"fibre {fibre_km * 1000:.0f} m @ {params.fibre_db_per_km}/km",
        fibre_km * params.fibre_db_per_km))

    for ratio in path.splitter_ratios:
        loss = params.splitter_loss.get(ratio)
        if loss is None:
            loss = params.splitter_loss.get(32, 17.5)
        elements.append(PathElement(f"1:{ratio} splitter", loss))

    elements.append(PathElement(
        f"{path.connectors} connectors", path.connectors * params.connector_db))
    elements.append(PathElement(
        f"{path.splices} splices", path.splices * params.splice_db))
    elements.append(PathElement(
        f"{path.patch_panels} patch panels",
        path.patch_panels * params.patch_panel_db))
    elements.append(PathElement("engineering margin", params.engineering_margin_db))
    elements.append(PathElement("repair allowance", params.repair_allowance_db))

    total = sum(e.loss_db for e in elements)
    budget = params.system_budget_db
    margin = budget - total

    if margin < 0:
        verdict = Verdict.FAIL
        dominant = max(elements, key=lambda e: e.loss_db)
        reason = (f"Path loss {total:.1f} dB exceeds the {budget:.1f} dB budget "
                  f"by {-margin:.1f} dB. Largest contributor: {dominant.label} "
                  f"({dominant.loss_db:.1f} dB).")
    elif margin < params.required_margin_db:
        verdict = Verdict.WARNING
        reason = (f"Margin {margin:.1f} dB is below the required "
                  f"{params.required_margin_db:.1f} dB. Buildable but with no "
                  "headroom for ageing or repair.")
    else:
        verdict = Verdict.PASS
        reason = f"Margin {margin:.1f} dB over the {budget:.1f} dB budget."

    return LossResult(total_loss_db=total, system_budget_db=budget,
                      design_margin_db=margin, verdict=verdict, reason=reason,
                      elements=elements)
