from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field


class DeploymentTaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    area: str = "other"
    status: str = "not_started"
    assignee_id: UUID | None = None
    start_date: date | None = None
    end_date: date | None = None
    updates: str | None = None
    issues: str | None = None
    entity_type: str | None = None
    entity_id: UUID | None = None


class DeploymentTaskUpdate(BaseModel):
    """Every field optional — only what's explicitly set is applied
    (exclude_unset), so a self-updating assignee sending just {"status": ...}
    doesn't accidentally clear everything else."""
    title: str | None = Field(default=None, min_length=1, max_length=300)
    area: str | None = None
    status: str | None = None
    assignee_id: UUID | None = None
    start_date: date | None = None
    end_date: date | None = None
    updates: str | None = None
    issues: str | None = None
    entity_type: str | None = None
    entity_id: UUID | None = None
