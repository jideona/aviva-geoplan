import uuid

from geoalchemy2 import Geometry
from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin, UUIDMixin


class Parcel(UUIDMixin, TimestampMixin, Base):
    """An estate or compound perimeter — the property demarcation.

    The network is built to this boundary; the drop from boundary to unit is
    installed at customer signup. Reach to the perimeter, not distance to a
    building centroid, is what determines whether a property is passed.
    """
    __tablename__ = "parcel"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False, index=True)
    parcel_code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_name: Mapped[str | None] = mapped_column(String(400))
    survey_code: Mapped[str | None] = mapped_column(String(20), index=True)

    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=True),
        nullable=False)
    area_sqm: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    perimeter_m: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    # Nearest point on the boundary to the serving road — the demarcation the
    # build terminates at. Populated during design.
    access_point: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True))

    building_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    marker_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    declared_units: Mapped[int | None] = mapped_column(Integer)
    observed_units: Mapped[int | None] = mapped_column(Integer)

    street_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("street.id", ondelete="SET NULL"))
    data_source_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("data_source.id", ondelete="SET NULL"))
    licence_class: Mapped[str] = mapped_column(
        String(30), nullable=False, default="owned")
    verification_state: Mapped[str] = mapped_column(
        String(30), nullable=False, default="field_observed")
    notes: Mapped[str | None] = mapped_column(Text)
