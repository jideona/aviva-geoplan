from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class BoundaryOut(BaseModel):
    id: UUID
    project_id: UUID
    area_sqkm: float
    source_filename: str
    verification_state: str
    created_at: datetime
    geometry: dict[str, Any]
