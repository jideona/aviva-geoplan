import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin, UUIDMixin

# Licence classes drive export gating (SAD 5.5).
LICENCE_CLASSES = ("share_alike", "attribution", "proprietary_restricted",
                   "owned", "licensed_authority", "tile_service")

SOURCE_TYPES = ("external_import", "overture", "osm", "open_buildings",
                "microsoft_gbf", "grid3", "ai_detection", "field_survey",
                "drone_capture", "manual_entry")


class DataSource(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "data_source"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    licence: Mapped[str | None] = mapped_column(String(120))
    licence_class: Mapped[str] = mapped_column(
        String(30), nullable=False, default="owned")
    attribution_text: Mapped[str | None] = mapped_column(Text)
    source_date: Mapped[date | None] = mapped_column(Date)
    # Role the source is admitted for (SRD 2.6). A source may not be used
    # outside the role recorded here.
    admitted_role: Mapped[str | None] = mapped_column(Text)


class ProvenanceRecord(UUIDMixin, TimestampMixin, Base):
    """Polymorphic: one row per entity per contributing source."""
    __tablename__ = "provenance_record"

    entity_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True)
    data_source_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("data_source.id", ondelete="RESTRICT"),
        nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))
    external_id: Mapped[str | None] = mapped_column(String(200), index=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
