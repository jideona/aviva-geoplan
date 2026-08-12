"""A field survey session — who went out, when, on which device.

Every mobile-captured record (manhole, building edit, media) can reference the
session it came from, so a day's fieldwork is traceable end to end and feeds the
audit trail.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin, UUIDMixin


class SurveySession(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "survey_session"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False, index=True)
    client_id: Mapped[str | None] = mapped_column(String(64), index=True)
    surveyor_email: Mapped[str | None] = mapped_column(String(200))
    device: Mapped[str | None] = mapped_column(String(120))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
