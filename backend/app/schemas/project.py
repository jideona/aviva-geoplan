from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.project import NETWORK_TECHNOLOGIES, PROJECT_STATUSES, PROJECT_TYPES


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    district: str = Field(min_length=2, max_length=100)
    client: str | None = None
    country: str = Field(default="NG", min_length=2, max_length=2)
    state: str | None = None
    city: str | None = None
    metric_crs_epsg: int = 32632
    project_type: str = "ftth"
    network_technology: str = "xgs_pon"
    design_capacity: int | None = Field(default=None, ge=0)
    expected_takeup_rate: float | None = Field(default=None, ge=0, le=1)
    design_horizon: date | None = None
    notes: str | None = None

    def validate_enums(self) -> list[str]:
        errors = []
        if self.project_type not in PROJECT_TYPES:
            errors.append(f"project_type must be one of {PROJECT_TYPES}")
        if self.network_technology not in NETWORK_TECHNOLOGIES:
            errors.append(f"network_technology must be one of {NETWORK_TECHNOLOGIES}")
        return errors


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    client: str | None = None
    state: str | None = None
    city: str | None = None
    design_capacity: int | None = Field(default=None, ge=0)
    expected_takeup_rate: float | None = Field(default=None, ge=0, le=1)
    design_horizon: date | None = None
    status: str | None = None
    notes: str | None = None

    def validate_enums(self) -> list[str]:
        if self.status is not None and self.status not in PROJECT_STATUSES:
            return [f"status must be one of {PROJECT_STATUSES}"]
        return []


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    client: str | None
    country: str
    state: str | None
    city: str | None
    district: str
    code_prefix: str
    metric_crs_epsg: int
    project_type: str
    network_technology: str
    design_capacity: int | None
    expected_takeup_rate: float | None
    design_horizon: date | None
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime
    has_boundary: bool = False
    boundary_area_sqkm: float | None = None
