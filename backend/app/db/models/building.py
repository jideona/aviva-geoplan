import uuid
from datetime import date

from geoalchemy2 import Geometry
from sqlalchemy import (Boolean, Date, ForeignKey, Integer, Numeric, String,
                        Text, UniqueConstraint)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin, UUIDMixin

BUILDING_TYPES = (
    "bungalow", "duplex", "detached_house", "semi_detached", "terrace",
    "townhouse", "apartment_block", "mixed_use", "commercial", "school",
    "hospital", "hotel", "government", "religious", "warehouse", "industrial",
    "secondary_structure", "other", "unclassified",
)
USE_TYPES = ("residential", "commercial", "mixed", "institutional", "unknown")


class Building(UUIDMixin, TimestampMixin, Base):
    """The canonical building record.

    One geometry per real-world building, retaining the lineage of every source
    that contributed. Height is deliberately split: a modelled value from a
    raster must never occupy the same column as a surveyed measurement
    (SAD 6.5, SRD FR-IMP-042).
    """
    __tablename__ = "building"
    __table_args__ = (
        UniqueConstraint("project_id", "building_code", name="uq_building_code"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False, index=True)
    street_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("street.id", ondelete="SET NULL"), index=True)
    serving_zone_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("serving_zone.id", ondelete="SET NULL"),
        index=True)
    parcel_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("parcel.id", ondelete="SET NULL"),
        index=True)
    building_code: Mapped[str | None] = mapped_column(String(40))

    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=True), nullable=False)
    centroid: Mapped[object] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True), nullable=False)
    footprint_area_sqm: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    perimeter_m: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    building_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="unclassified")
    use_type: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
    name: Mapped[str | None] = mapped_column(String(200))
    # Captured in the field by a surveyor (street + number / plot description).
    address: Mapped[str | None] = mapped_column(String(300))

    floors_reported: Mapped[int | None] = mapped_column(Integer)
    height_measured_m: Mapped[float | None] = mapped_column(Numeric(8, 2))
    # Modelled height and its dispersion. Never merged with the measured column.
    height_modelled_m: Mapped[float | None] = mapped_column(Numeric(8, 2))
    height_modelled_cells: Mapped[int | None] = mapped_column(Integer)
    height_modelled_stddev: Mapped[float | None] = mapped_column(Numeric(8, 2))
    height_modelled_year: Mapped[int | None] = mapped_column(Integer)

    units_surveyed: Mapped[int | None] = mapped_column(Integer)
    premises_estimated: Mapped[int | None] = mapped_column(Integer)
    premises_estimate_low: Mapped[int | None] = mapped_column(Integer)
    premises_estimate_high: Mapped[int | None] = mapped_column(Integer)
    estimation_model_version: Mapped[str | None] = mapped_column(String(40))

    data_source_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("data_source.id", ondelete="SET NULL"))
    external_id: Mapped[str | None] = mapped_column(String(200), index=True)
    source_dataset: Mapped[str | None] = mapped_column(String(80))
    source_update_date: Mapped[date | None] = mapped_column(Date)
    licence_class: Mapped[str] = mapped_column(
        String(30), nullable=False, default="proprietary_restricted")
    detection_confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))

    # Street assignment carries its own confidence and rationale so that a
    # reviewer can see why, not just what (SRD FR-STA-004).
    street_assignment_confidence: Mapped[float | None] = mapped_column(Numeric(5, 3))
    street_assignment_reason: Mapped[str | None] = mapped_column(String(200))
    street_assignment_distance_m: Mapped[float | None] = mapped_column(Numeric(10, 2))

    # How the drop reaches this building: 'aerial' | 'underground' | None.
    # None means undecided — the project's aerial_drop_share assumption applies
    # in the SOM/BOQ until a surveyor or planner sets it.
    drop_deployment: Mapped[str | None] = mapped_column(String(12))

    verification_state: Mapped[str] = mapped_column(
        String(30), nullable=False, default="imported", index=True)
    survey_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="not_surveyed")
    notes: Mapped[str | None] = mapped_column(Text)
    # Excluded buildings (non-serviceable: sheds, ruins, mis-detections) are
    # hidden from the map, register and design but kept for audit — reversible,
    # unlike a hard delete of original data.
    excluded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                           index=True)
    excluded_reason: Mapped[str | None] = mapped_column(String(200))
    # Source attributes not mapped onto a column are retained rather than lost.
    source_attributes: Mapped[dict | None] = mapped_column(JSONB)
