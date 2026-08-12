from typing import Any
from uuid import UUID

from pydantic import BaseModel


class ImportSummary(BaseModel):
    created: int
    updated: int
    unchanged: int
    skipped_outside_boundary: int
    skipped_too_small: int
    skipped_protected: int
    invalid_geometry: int
    licence_classes: dict[str, int]
    datasets: dict[str, int]
    share_alike_present: bool


class BuildingOut(BaseModel):
    id: UUID
    building_code: str | None
    street_id: UUID | None
    street_name: str | None
    footprint_area_sqm: float
    building_type: str
    use_type: str
    floors_reported: int | None
    premises_estimated: int | None
    units_surveyed: int | None
    source_dataset: str | None
    licence_class: str
    verification_state: str
    survey_status: str


class StreetOut(BaseModel):
    id: UUID
    street_code: str
    name: str | None
    name_state: str
    name_source: str | None
    length_m: float
    road_class: str
    licence_class: str
    verification_state: str
    building_count: int


class FeatureCollection(BaseModel):
    type: str = "FeatureCollection"
    features: list[dict[str, Any]]


class LicenceSummary(BaseModel):
    total: int
    by_class: dict[str, int]
    share_alike_count: int
    share_alike_pct: float
    blocks_commercial_delivery: bool
    note: str
