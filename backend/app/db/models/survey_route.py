"""Field-walked route paths — a surveyor records a line by walking it.

Used to capture as-walked cable routes / trench paths / duct runs on site: the
mobile app logs GPS positions as the surveyor moves and saves the resulting
polyline here. Like manholes, this is field_surveyed (highest trust) and carries
a client-generated id so an offline capture replayed on reconnect is idempotent.
"""
import uuid

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin, UUIDMixin

ROUTE_TYPES = ("cable_route", "trench", "duct", "aerial", "walk", "other")


class SurveyRoute(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "survey_route"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False, index=True)
    client_id: Mapped[str | None] = mapped_column(String(64), index=True)
    code: Mapped[str | None] = mapped_column(String(40))
    route_type: Mapped[str] = mapped_column(String(20), nullable=False,
                                            default="cable_route")
    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="LINESTRING", srid=4326, spatial_index=True),
        nullable=False)
    length_m: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    point_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_accuracy_m: Mapped[float | None] = mapped_column(Numeric(6, 2))
    notes: Mapped[str | None] = mapped_column(Text)

    surveyed_by: Mapped[str | None] = mapped_column(String(200))
    survey_session_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("survey_session.id", ondelete="SET NULL"))
    licence_class: Mapped[str] = mapped_column(String(30), nullable=False,
                                               default="owned")
    verification_state: Mapped[str] = mapped_column(String(30), nullable=False,
                                                    default="field_observed")
    excluded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
