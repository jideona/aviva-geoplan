import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin, UUIDMixin


class DesignRun(UUIDMixin, TimestampMixin, Base):
    """One execution of the planning engine.

    Records the engine version, the full parameter set and the input counts, so
    any design can be reproduced or explained (SRD FR-RTE-011).
    """
    __tablename__ = "design_run"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False, index=True)
    engine_version: Mapped[str] = mapped_column(String(20), nullable=False)
    rules: Mapped[dict] = mapped_column(JSONB, nullable=False)
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False)
    warnings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    run_by: Mapped[str | None] = mapped_column(String(200))
    ran_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_current: Mapped[bool] = mapped_column(nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text)


class Fdh(UUIDMixin, TimestampMixin, Base):
    """Fibre distribution hub — holds the primary (single-stage) splitters."""
    __tablename__ = "fdh"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False, index=True)
    design_run_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("design_run.id", ondelete="CASCADE"),
        nullable=False, index=True)
    fdh_code: Mapped[str] = mapped_column(String(40), nullable=False)
    point: Mapped[object] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=False)
    fat_count: Mapped[int] = mapped_column(Integer, nullable=False)
    premises_count: Mapped[int] = mapped_column(Integer, nullable=False)
    splitters: Mapped[int] = mapped_column(Integer, nullable=False)
    splitter_ratio: Mapped[int] = mapped_column(Integer, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    utilisation_pct: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False)
    max_distribution_m: Mapped[float] = mapped_column(Numeric(10, 1), nullable=False)
    road_offset_m: Mapped[float | None] = mapped_column(Numeric(10, 1))


class ServingZone(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "serving_zone"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False, index=True)
    design_run_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("design_run.id", ondelete="CASCADE"),
        nullable=False, index=True)
    zone_code: Mapped[str] = mapped_column(String(40), nullable=False)
    fat_point: Mapped[object] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=False)
    # The convex hull of the buildings served — indicative extent, not a legal
    # boundary.
    extent: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=True))

    building_count: Mapped[int] = mapped_column(Integer, nullable=False)
    premises_count: Mapped[int] = mapped_column(Integer, nullable=False)
    splitter_ratio: Mapped[int] = mapped_column(Integer, nullable=False)
    usable_ports: Mapped[int] = mapped_column(Integer, nullable=False)
    spare_ports: Mapped[int] = mapped_column(Integer, nullable=False)
    utilisation_pct: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False)

    fdh_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("fdh.id", ondelete="SET NULL"))
    max_drop_m: Mapped[float] = mapped_column(Numeric(10, 1), nullable=False)
    avg_drop_m: Mapped[float] = mapped_column(Numeric(10, 1), nullable=False)
    road_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("street.id", ondelete="SET NULL"))
    road_offset_m: Mapped[float | None] = mapped_column(Numeric(10, 1))

    premises_assumed: Mapped[bool] = mapped_column(nullable=False, default=False)
    warnings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    locked: Mapped[bool] = mapped_column(nullable=False, default=False)
