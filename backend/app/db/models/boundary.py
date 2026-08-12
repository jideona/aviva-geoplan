import uuid

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin, UUIDMixin


class ProjectBoundary(UUIDMixin, TimestampMixin, Base):
    """Versioned. Superseding a boundary records a new row rather than
    overwriting, so that any design remains traceable to the extent it was
    produced under."""
    __tablename__ = "project_boundary"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False, index=True)
    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=True),
        nullable=False)
    area_sqkm: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    verification_state: Mapped[str] = mapped_column(
        String(30), nullable=False, default="imported")
