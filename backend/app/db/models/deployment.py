"""Deployment task tracking — the project-management layer GeoPlan didn't
have (see GeoPlan_Deployment_PM_Proposal.docx, phase 1). Replaces the
"Deployment plan" monday.com board for a project: area, status, owner, dates,
free-text updates/issues.

A task can optionally point at a real GeoPlan entity (an FDH, a FAT/serving
zone, a street, a manhole) using the same polymorphic (entity_type, entity_id)
pattern MediaAsset already uses — that link is what lets a task drop a pin on
its actual map location instead of living in a spreadsheet row with no
coordinates. Not a hard FK on purpose, for the same reason MediaAsset isn't:
one column pair serves every entity type this might ever point at.
"""
import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin, UUIDMixin

TASK_AREAS = ("ug_network", "access", "other")
TASK_STATUSES = ("not_started", "in_progress", "blocked", "done")
# Entities a task is allowed to point at — kept in sync with what actually
# exists in the domain model, not open-ended, so a typo'd entity_type can't
# silently produce a dead link.
TASK_ENTITY_TYPES = ("fdh", "serving_zone", "street", "manhole", "building",
                     "corridor")


class DeploymentTask(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "deployment_task"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    area: Mapped[str] = mapped_column(String(20), nullable=False,
                                      default="other", index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False,
                                        default="not_started", index=True)

    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"),
        index=True)

    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)

    updates: Mapped[str | None] = mapped_column(Text)
    issues: Mapped[str | None] = mapped_column(Text)

    entity_type: Mapped[str | None] = mapped_column(String(40), index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True),
                                                        index=True)

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"))
