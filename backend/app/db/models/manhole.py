"""Surveyed manhole / chamber assets.

The planning engine COMPUTES a chamber schedule (how many handholes/manholes a
route implies). This is different: a real, field-surveyed chamber with a GPS
location, a type, a condition assessment and photos/video — captured by a
surveyor on the mobile app. Field capture is the highest-trust source
(field_surveyed → OWNED), so it supersedes computed or desk data with full
provenance.
"""
import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin, UUIDMixin

MANHOLE_TYPES = ("handhole", "manhole", "joint_chamber", "footway_box", "other")
CONDITIONS = ("good", "fair", "poor", "damaged", "buried", "inaccessible", "unknown")


class Manhole(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "manhole"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False, index=True)
    # Client-generated id from the mobile app, so an offline create replayed on
    # reconnect is idempotent (never duplicates).
    client_id: Mapped[str | None] = mapped_column(String(64), index=True)
    code: Mapped[str | None] = mapped_column(String(40))
    manhole_type: Mapped[str] = mapped_column(String(20), nullable=False,
                                              default="manhole")
    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=False)
    gps_accuracy_m: Mapped[float | None] = mapped_column(Numeric(6, 2))

    condition: Mapped[str] = mapped_column(String(20), nullable=False,
                                           default="unknown")
    condition_notes: Mapped[str | None] = mapped_column(Text)
    assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    surveyed_by: Mapped[str | None] = mapped_column(String(200))
    survey_session_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("survey_session.id", ondelete="SET NULL"))

    licence_class: Mapped[str] = mapped_column(String(30), nullable=False,
                                               default="owned")
    verification_state: Mapped[str] = mapped_column(String(30), nullable=False,
                                                    default="field_observed")
    excluded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
