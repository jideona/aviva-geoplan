"""FAT service-area coverage and property-type inference.

Produces a per-FAT breakdown of what is served, distinguishing confirmed data
(a building inside a surveyed parcel with an observed unit count) from
estimated data (type and units inferred from footprint geometry). The two are
never mixed silently: every estimated figure is labelled and scored.
"""
from dataclasses import dataclass, field
from enum import Enum


class PropertyType(str, Enum):
    SINGLE_HOME = "single_home"          # bungalow, detached, standalone
    SECONDARY = "secondary_structure"    # BQ, outbuilding, kiosk
    DUPLEX = "duplex"                    # 2 units, one structure
    TERRACE = "terrace"                 # row of joined units
    APARTMENT_BLOCK = "apartment_block"  # multi-unit block of flats
    COMMERCIAL = "commercial"           # plaza, retail, office
    UNKNOWN = "unknown"


class DataQuality(str, Enum):
    CONFIRMED = "confirmed"     # from survey: parcel with observed units
    ESTIMATED = "estimated"     # inferred from footprint geometry


# Footprint-area thresholds (m², in the metric CRS) for the inference fallback.
# Calibrated to the Wuye February survey: median footprint 35 m², the dominant
# block of flats around 200-400 m². Revisit as survey coverage grows.
def infer_type(area_sqm: float, neighbours_similar: int) -> tuple[PropertyType, float]:
    """Best-guess property type from footprint alone, with a confidence.

    Confidence is deliberately modest — footprint geometry is a weak signal for
    unit count, which is exactly why field survey exists.
    """
    if area_sqm < 30:
        return PropertyType.SECONDARY, 0.55
    if area_sqm < 90:
        # A run of similar small footprints is a terrace, not detached homes.
        if neighbours_similar >= 3:
            return PropertyType.TERRACE, 0.5
        return PropertyType.SINGLE_HOME, 0.55
    if area_sqm < 160:
        if neighbours_similar >= 3:
            return PropertyType.TERRACE, 0.55
        return PropertyType.DUPLEX, 0.45
    if area_sqm < 450:
        return PropertyType.APARTMENT_BLOCK, 0.5
    return PropertyType.COMMERCIAL, 0.45


# Units per property type when no survey figure exists. Ranges, not points,
# because the whole reason for estimating is that we do not know.
ESTIMATED_UNITS: dict[PropertyType, tuple[int, int, int]] = {
    # type: (low, likely, high)
    PropertyType.SECONDARY: (1, 1, 1),
    PropertyType.SINGLE_HOME: (1, 1, 2),
    PropertyType.DUPLEX: (1, 2, 2),
    PropertyType.TERRACE: (1, 1, 1),         # per terrace unit footprint
    PropertyType.APARTMENT_BLOCK: (4, 6, 12),  # Wuye median block is 6
    PropertyType.COMMERCIAL: (1, 1, 40),
    PropertyType.UNKNOWN: (1, 1, 1),
}


@dataclass
class BuildingAssessment:
    building_id: str
    area_sqm: float
    property_type: PropertyType
    quality: DataQuality
    units_low: int
    units_likely: int
    units_high: int
    confidence: float
    parcel_name: str | None = None
    basis: str = ""


@dataclass
class TypeBreakdown:
    property_type: PropertyType
    buildings: int
    confirmed_buildings: int
    estimated_buildings: int
    units_low: int
    units_likely: int
    units_high: int
    confidence: float


@dataclass
class FatCoverage:
    fat_code: str
    area_sqm: float
    building_count: int
    property_density_per_ha: float
    confirmed_buildings: int
    estimated_buildings: int
    confirmed_units: int
    estimated_units_likely: int
    estimated_units_low: int
    estimated_units_high: int
    breakdown: list[TypeBreakdown]
    estates_served: list[str]
    overall_confidence: float
    notes: list[str] = field(default_factory=list)

    @property
    def total_units_likely(self) -> int:
        return self.confirmed_units + self.estimated_units_likely

    @property
    def coverage_quality(self) -> str:
        if self.building_count == 0:
            return "empty"
        confirmed_pct = self.confirmed_buildings / self.building_count
        if confirmed_pct >= 0.8:
            return "confirmed"
        if confirmed_pct >= 0.2:
            return "mixed"
        return "estimated"


def assess_building(building_id: str, area_sqm: float,
                    neighbours_similar: int,
                    confirmed_units: int | None = None,
                    parcel_name: str | None = None) -> BuildingAssessment:
    """Confirmed count where survey supplies it; inference otherwise."""
    if confirmed_units is not None:
        # Type is still inferred, but the unit count is a fact.
        ptype, _ = infer_type(area_sqm, neighbours_similar)
        return BuildingAssessment(
            building_id=building_id, area_sqm=area_sqm, property_type=ptype,
            quality=DataQuality.CONFIRMED,
            units_low=confirmed_units, units_likely=confirmed_units,
            units_high=confirmed_units, confidence=1.0, parcel_name=parcel_name,
            basis=f"surveyed: {confirmed_units} units in {parcel_name or 'parcel'}")

    ptype, type_conf = infer_type(area_sqm, neighbours_similar)
    low, likely, high = ESTIMATED_UNITS[ptype]
    return BuildingAssessment(
        building_id=building_id, area_sqm=area_sqm, property_type=ptype,
        quality=DataQuality.ESTIMATED,
        units_low=low, units_likely=likely, units_high=high,
        confidence=round(type_conf, 2), parcel_name=parcel_name,
        basis=f"estimated from {area_sqm:.0f} m² footprint"
              + (f", {neighbours_similar} similar neighbours" if neighbours_similar else ""))


def summarise_fat(fat_code: str, area_sqm: float,
                  assessments: list[BuildingAssessment],
                  estates: list[str]) -> FatCoverage:
    by_type: dict[PropertyType, list[BuildingAssessment]] = {}
    for a in assessments:
        by_type.setdefault(a.property_type, []).append(a)

    breakdown = []
    for ptype, group in sorted(by_type.items(), key=lambda kv: -len(kv[1])):
        conf = [g for g in group if g.quality is DataQuality.CONFIRMED]
        est = [g for g in group if g.quality is DataQuality.ESTIMATED]
        breakdown.append(TypeBreakdown(
            property_type=ptype, buildings=len(group),
            confirmed_buildings=len(conf), estimated_buildings=len(est),
            units_low=sum(g.units_low for g in group),
            units_likely=sum(g.units_likely for g in group),
            units_high=sum(g.units_high for g in group),
            confidence=round(sum(g.confidence for g in group) / len(group), 2),
        ))

    confirmed = [a for a in assessments if a.quality is DataQuality.CONFIRMED]
    estimated = [a for a in assessments if a.quality is DataQuality.ESTIMATED]
    hectares = area_sqm / 10_000 if area_sqm else 0

    return FatCoverage(
        fat_code=fat_code, area_sqm=round(area_sqm, 1),
        building_count=len(assessments),
        property_density_per_ha=round(len(assessments) / hectares, 1) if hectares else 0,
        confirmed_buildings=len(confirmed),
        estimated_buildings=len(estimated),
        confirmed_units=sum(a.units_likely for a in confirmed),
        estimated_units_likely=sum(a.units_likely for a in estimated),
        estimated_units_low=sum(a.units_low for a in estimated),
        estimated_units_high=sum(a.units_high for a in estimated),
        breakdown=breakdown, estates_served=sorted(estates),
        overall_confidence=round(
            sum(a.confidence for a in assessments) / len(assessments), 2)
            if assessments else 0.0,
    )
