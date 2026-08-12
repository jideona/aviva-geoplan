import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin, UUIDMixin

MATCH_STATUSES = ("unmatched", "proposed", "confirmed", "not_found")


class RecordedStreet(UUIDMixin, TimestampMixin, Base):
    """A street name captured in the field, awaiting a geometry match.

    Distance alone cannot identify which road a recorded name belongs to —
    tested on known cases it resolved 0 of 5 uniquely. So the name is held
    here until a human matches it on the map, rather than guessed.
    """
    __tablename__ = "recorded_street"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    recorded_length_m: Mapped[float | None] = mapped_column(Numeric(10, 1))
    survey_date: Mapped[date | None] = mapped_column(Date)
    surveyor: Mapped[str | None] = mapped_column(String(200))
    source_file: Mapped[str | None] = mapped_column(String(255))

    matched_street_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("street.id", ondelete="SET NULL"))
    match_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unmatched", index=True)
    matched_by: Mapped[str | None] = mapped_column(String(200))
    length_delta_pct: Mapped[float | None] = mapped_column(Numeric(8, 2))
    note: Mapped[str | None] = mapped_column(Text)


class PremisesObservation(UUIDMixin, TimestampMixin, Base):
    """An observed unit count. The calibration input for premises estimation.

    One row per group of identical buildings, as recorded in the field
    ("11 buildings of 6 units"). No open data source supplies this.
    """
    __tablename__ = "premises_observation"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False, index=True)
    estate_name: Mapped[str] = mapped_column(String(255), nullable=False)
    building_count: Mapped[int] = mapped_column(Integer, nullable=False)
    units_per_building: Mapped[int] = mapped_column(Integer, nullable=False)
    typology: Mapped[str] = mapped_column(String(20), nullable=False,
                                          default="unknown", index=True)
    street_hint: Mapped[str | None] = mapped_column(String(200))
    building_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("building.id", ondelete="SET NULL"))
    survey_date: Mapped[date | None] = mapped_column(Date)
    surveyor: Mapped[str | None] = mapped_column(String(200))
    source_file: Mapped[str | None] = mapped_column(String(255))
    verification_state: Mapped[str] = mapped_column(
        String(30), nullable=False, default="field_observed")
    note: Mapped[str | None] = mapped_column(Text)
