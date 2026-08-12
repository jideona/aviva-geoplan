"""Drop corridors — traced footpaths, pathways, fence lines and service ways
that a drop cable can follow but that are NOT streets.

Kept separate from Street on purpose: feeder and distribution plant is trenched
along the carriageway, so those routes must only see streets. A drop, by
contrast, is often strung along a fence or run down an internal footpath that no
vehicle uses. Mixing the two networks would trench feeder down a garden fence.
Corridors therefore feed the drop-routing graph only.

Provenance mirrors buildings: a line traced over display-only Esri imagery is a
derivative of that imagery (desk_reference_restricted, pilot-only); one traced
over Aviva's own drone orthomosaic, or walked, is clean.
"""
import uuid

from geoalchemy2 import Geometry
from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin, UUIDMixin

CORRIDOR_TYPES = ("footpath", "pathway", "fence", "service", "other")


class Corridor(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "corridor"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False, index=True)
    corridor_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="footpath")
    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="LINESTRING", srid=4326, spatial_index=True),
        nullable=False)
    length_m: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    capture_source: Mapped[str] = mapped_column(String(30), nullable=False)
    licence_class: Mapped[str] = mapped_column(
        String(30), nullable=False, default="desk_reference_restricted")
    verification_state: Mapped[str] = mapped_column(
        String(30), nullable=False, default="desk_verified")
    commercial_ready: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(200))
