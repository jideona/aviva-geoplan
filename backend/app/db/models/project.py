import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin, UUIDMixin

PROJECT_TYPES = ("ftth", "fttb", "metro_fibre", "enterprise_fibre",
                 "backbone_fibre", "maintenance_survey", "network_audit")
NETWORK_TECHNOLOGIES = ("gpon", "xgs_pon", "combo_pon", "point_to_point")
PROJECT_STATUSES = ("draft", "survey", "design", "approved", "construction",
                    "as_built", "archived")


class Project(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "project"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("organisation.id", ondelete="RESTRICT"),
        nullable=False, index=True)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"),
        nullable=False)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    client: Mapped[str | None] = mapped_column(String(200))
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="NG")
    state: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(100))
    district: Mapped[str] = mapped_column(String(100), nullable=False)

    # Identifier prefix derived from the district, e.g. WUY. Immutable.
    code_prefix: Mapped[str] = mapped_column(String(3), nullable=False)

    # Geometry is always stored in EPSG:4326 (SAD ADR-001). This is the CRS used
    # for measurement only.
    metric_crs_epsg: Mapped[int] = mapped_column(Integer, nullable=False, default=32632)

    project_type: Mapped[str] = mapped_column(String(30), nullable=False, default="ftth")
    network_technology: Mapped[str] = mapped_column(
        String(20), nullable=False, default="xgs_pon")
    design_capacity: Mapped[int | None] = mapped_column(Integer)
    # Share of UNFLAGGED drops assumed aerial in the SOM/BOQ (0..1). Buildings
    # with an explicit drop_deployment are never subject to this assumption;
    # at 0 every unflagged drop prices as underground.
    aerial_drop_share: Mapped[float] = mapped_column(
        Numeric(4, 3), nullable=False, default=0)
    expected_takeup_rate: Mapped[float | None] = mapped_column(Numeric(5, 4))
    design_horizon: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    notes: Mapped[str | None] = mapped_column(Text)
