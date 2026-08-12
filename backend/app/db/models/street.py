import uuid

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin, UUIDMixin

NAME_STATUSES = ("named", "provisional", "unnamed")

ROAD_CLASSES = ("motorway", "trunk", "primary", "secondary", "tertiary",
                "residential", "service", "track", "footway", "unknown")


class Street(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "street"
    __table_args__ = (
        UniqueConstraint("project_id", "street_code", name="uq_street_code"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False, index=True)
    street_code: Mapped[str] = mapped_column(String(30), nullable=False)
    # Nullable by design: in Wuye the road geometry is largely present while
    # the names are mostly absent. Discarding unnamed roads would discard the
    # network that makes street assignment possible.
    name: Mapped[str | None] = mapped_column(String(200))
    name_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unnamed")
    # Where the name came from. Determines licence class and whether the
    # record may be redistributed (app.domain.naming).
    name_source: Mapped[str | None] = mapped_column(String(30))
    name_recorded_by: Mapped[str | None] = mapped_column(String(200))
    name_evidence_key: Mapped[str | None] = mapped_column(String(500))
    name_note: Mapped[str | None] = mapped_column(Text)
    needs_field_name: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True)
    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="MULTILINESTRING", srid=4326, spatial_index=True),
        nullable=False)
    length_m: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    road_class: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")

    data_source_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("data_source.id", ondelete="SET NULL"))
    external_id: Mapped[str | None] = mapped_column(String(200), index=True)
    licence_class: Mapped[str] = mapped_column(String(30), nullable=False, default="owned")
    verification_state: Mapped[str] = mapped_column(
        String(30), nullable=False, default="imported")
