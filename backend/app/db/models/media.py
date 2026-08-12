"""Media attachments (photos / videos) stored in object storage (MinIO).

A media asset links to any entity — a manhole, a building, a street — by a
polymorphic (entity_type, entity_id) pair. The bytes live in MinIO under
object_key; this row is the metadata and the link. Upload is two-phase: the API
issues a presigned PUT URL, the device uploads the bytes directly to MinIO, then
confirms — so large photos/videos never pass through the application server.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin, UUIDMixin

MEDIA_KINDS = ("photo", "video")


class MediaAsset(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "media_asset"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False, index=True)
    # Polymorphic owner — not a hard FK, so one media table serves every asset.
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True),
                                                 nullable=False, index=True)
    client_id: Mapped[str | None] = mapped_column(String(64), index=True)

    kind: Mapped[str] = mapped_column(String(10), nullable=False, default="photo")
    object_key: Mapped[str] = mapped_column(String(400), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(80))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    caption: Mapped[str | None] = mapped_column(Text)

    # Capture context — a photo is evidence, so where/when it was taken matters.
    captured_lat: Mapped[float | None] = mapped_column(Numeric(9, 6))
    captured_lon: Mapped[float | None] = mapped_column(Numeric(9, 6))
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    captured_by: Mapped[str | None] = mapped_column(String(200))
    survey_session_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("survey_session.id", ondelete="SET NULL"))

    uploaded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
