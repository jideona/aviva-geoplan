"""Quick field photo capture of a building — a surveyor snaps a photo and the
app auto-captures the GPS location, no building record lookup required.

Deliberately NOT the same thing as editing an existing Building record via
building_edit_service (that requires finding/picking a footprint from the
imported dataset and edits its attributes). This is a fast, standalone point
capture — the photo is the primary content, the location is just where it was
taken. Like Manhole/SurveyRoute, field capture is the highest-trust source and
carries a client-generated id so an offline capture replayed on reconnect is
idempotent.
"""
import uuid

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin, UUIDMixin


class BuildingPhoto(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "building_photo"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False, index=True)
    # Client-generated id from the mobile app, so an offline create replayed on
    # reconnect is idempotent (never duplicates).
    client_id: Mapped[str | None] = mapped_column(String(64), index=True)
    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=False)
    gps_accuracy_m: Mapped[float | None] = mapped_column(Numeric(6, 2))
    surveyed_by: Mapped[str | None] = mapped_column(String(200))
    licence_class: Mapped[str] = mapped_column(String(30), nullable=False,
                                               default="owned")
    verification_state: Mapped[str] = mapped_column(String(30), nullable=False,
                                                    default="field_observed")
    # Not exposed in the app yet (no move/delete on this capture type today),
    # kept for parity with Manhole/SurveyRoute so adding that later needs no
    # migration.
    excluded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
