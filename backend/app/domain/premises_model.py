"""Premises estimation, fitted on observed unit counts (SRD FR-PRM-007/008).

No open data source states how many serviceable units a building contains.
Only survey does. This module turns observations into an estimator, and — as
importantly — refuses to produce a district figure the sample cannot support.
"""
import statistics as stats
from dataclasses import dataclass, field
from enum import Enum


class Typology(str, Enum):
    SINGLE = "single"            # 1 unit: bungalow, detached, terrace unit
    SMALL_MULTI = "small_multi"  # 2-3: duplex, small terrace
    BLOCK = "block"              # 4-8: the dominant Wuye block of flats
    LARGE_BLOCK = "large_block"  # 9-15
    TOWER = "tower"              # 16+: plaza, tower, commercial MDU
    UNKNOWN = "unknown"


BANDS: list[tuple[Typology, int, int]] = [
    (Typology.SINGLE, 1, 1),
    (Typology.SMALL_MULTI, 2, 3),
    (Typology.BLOCK, 4, 8),
    (Typology.LARGE_BLOCK, 9, 15),
    (Typology.TOWER, 16, 10_000),
]

# Below this a band's estimate is reported but flagged as weakly evidenced.
# Thirty is the point at which an interquartile range over a skewed count
# distribution starts to mean something. The February 2025 Wuye survey has
# exactly 20 observations in the large-block band, which is why this is not
# set to 20 — that band should read as thin, because it is.
MIN_SAMPLE = 30


def band_for_units(units: int) -> Typology:
    for typ, lo, hi in BANDS:
        if lo <= units <= hi:
            return typ
    return Typology.UNKNOWN


@dataclass
class Observation:
    """One independently observed group of identical buildings.

    Field method: count the buildings in an estate, then record how many units
    each contains — "13 buildings of 8 apartments". That is ONE observation
    covering 13 buildings, not 13 observations. Expanding it to 13 rows and
    treating them as independent would overstate the evidence roughly
    threefold in the dominant band.
    """
    units: int
    building_count: int = 1
    typology: Typology | None = None
    label: str | None = None

    def band(self) -> Typology:
        return self.typology or band_for_units(self.units)


@dataclass
class BandEstimate:
    typology: Typology
    sample_size: int          # independent observations
    buildings_covered: int    # buildings those observations account for
    median: float
    mean: float
    p25: float
    p75: float
    minimum: int
    maximum: int
    well_evidenced: bool
    distinct_estates: int = 0

    def interval(self) -> tuple[float, float]:
        return (self.p25, self.p75)

    @property
    def replication(self) -> float:
        """Buildings per independent observation. High values mean a tight
        interval reflects uniform estate design, not corroboration."""
        return round(self.buildings_covered / self.sample_size, 1) if self.sample_size else 0.0


@dataclass
class PremisesModel:
    version: str
    bands: dict[Typology, BandEstimate] = field(default_factory=dict)
    total_observations: int = 0     # independent counts
    total_buildings: int = 0        # buildings those counts cover

    def estimate(self, typology: Typology) -> BandEstimate | None:
        return self.bands.get(typology)

    def point_estimate(self, typology: Typology) -> float | None:
        b = self.bands.get(typology)
        return b.median if b else None


def fit(observations: list[Observation], version: str) -> PremisesModel:
    """Fit per typology, weighting by independent observation, not by building.

    Statistics are computed over the observations themselves. A single estate
    of 26 identical bungalows is one piece of evidence about bungalows, not 26.
    """
    grouped: dict[Typology, list[Observation]] = {}
    for obs in observations:
        grouped.setdefault(obs.band(), []).append(obs)

    model = PremisesModel(
        version=version,
        total_observations=len(observations),
        total_buildings=sum(o.building_count for o in observations),
    )
    for typ, group in grouped.items():
        values = sorted(o.units for o in group)
        n = len(values)
        model.bands[typ] = BandEstimate(
            typology=typ, sample_size=n,
            buildings_covered=sum(o.building_count for o in group),
            median=stats.median(values), mean=round(stats.fmean(values), 2),
            p25=values[max(0, n // 4)], p75=values[min(n - 1, 3 * n // 4)],
            minimum=values[0], maximum=values[-1],
            well_evidenced=n >= MIN_SAMPLE,
            distinct_estates=len({o.label for o in group if o.label}),
        )
    return model


def sampling_bias(model: PremisesModel,
                  register_mix: dict[Typology, int]) -> dict:
    """Compare the surveyed typology mix against the register's.

    A survey that walked estates will over-represent blocks of flats. Applying
    its mean to the whole register would overstate the addressable market — the
    single figure an ISP will scrutinise hardest.
    """
    surveyed_total = model.total_buildings or model.total_observations
    register_total = sum(register_mix.values())
    if not surveyed_total or not register_total:
        return {"comparable": False,
                "note": "Not enough data on one side to compare."}

    rows = []
    max_divergence = 0.0
    for typ, _, _ in BANDS:
        s = model.bands[typ].buildings_covered if typ in model.bands else 0
        r = register_mix.get(typ, 0)
        s_pct = s / surveyed_total * 100
        r_pct = r / register_total * 100
        rows.append({"typology": typ.value, "surveyed_pct": round(s_pct, 1),
                     "register_pct": round(r_pct, 1),
                     "divergence_pp": round(s_pct - r_pct, 1)})
        max_divergence = max(max_divergence, abs(s_pct - r_pct))

    representative = max_divergence < 10.0
    return {
        "comparable": True,
        "representative": representative,
        "max_divergence_pp": round(max_divergence, 1),
        "rows": rows,
        "note": (
            "The surveyed mix tracks the register; a district total from this "
            "model is defensible."
        ) if representative else (
            "The surveyed mix diverges materially from the register. This model "
            "may be applied per typology, but a district total derived from it "
            "would be misleading until the survey covers the under-sampled bands."
        ),
    }


def district_total(model: PremisesModel, register_mix: dict[Typology, int],
                   bias: dict, spatial_coverage: dict | None = None) -> dict:
    """A district premises total, produced only where the sample supports it.

    Two independent gates. A sample can match the register's typology mix and
    still come entirely from one corner of the district, so spatial coverage is
    checked separately — matching the mix is not the same as covering the ground.
    """
    if not bias.get("representative"):
        return {
            "available": False,
            "reason": bias.get("note", "Sample is not representative."),
        }
    if spatial_coverage and spatial_coverage.get("available"):
        if not spatial_coverage.get("spatially_representative", True):
            return {
                "available": False,
                "reason": (
                    f"Typology mix is representative, but survey coverage "
                    f"reaches only {spatial_coverage.get('coverage_pct', 0)}% of "
                    f"buildings and "
                    f"{spatial_coverage.get('cells_without_coverage', 0)} of "
                    f"{spatial_coverage.get('cells_total', 0)} areas have no "
                    "observations at all. A district total would extrapolate "
                    "one part of the district over the rest."
                ),
            }
    low = high = point = 0.0
    unclassified = register_mix.get(Typology.UNKNOWN, 0)
    for typ, count in register_mix.items():
        est = model.estimate(typ)
        if est is None or typ is Typology.UNKNOWN:
            continue
        point += est.median * count
        low += est.p25 * count
        high += est.p75 * count
    return {
        "available": True,
        "premises_estimate": round(point),
        "interval_low": round(low),
        "interval_high": round(high),
        "unclassified_buildings": unclassified,
        "note": ("Interval is the interquartile range of observed counts, not a "
                 "confidence interval. Buildings of unknown typology are excluded."),
    }
