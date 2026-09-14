"""Links a Building to nearby Manhole records it's actually served by or
associated with in the field -- the "Associated Assets" a surveyor can attach
while updating a building (added for the field-app redesign's Update
Building screen). Deliberately a real join table rather than two nullable FK
columns on Building, so a building isn't artificially capped at a fixed
number of linked manholes even though today's mobile UI only offers two
picker slots.
"""
import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin, UUIDMixin


class BuildingManholeLink(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "building_manhole_link"
    __table_args__ = (
        UniqueConstraint("building_id", "manhole_id", name="uq_building_manhole_link"),
    )

    building_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("building.id", ondelete="CASCADE"),
        nullable=False, index=True)
    manhole_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("manhole.id", ondelete="CASCADE"),
        nullable=False, index=True)
    created_by: Mapped[str | None] = mapped_column(String(200))
