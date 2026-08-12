import uuid

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin, UUIDMixin


class StockItem(Base, UUIDMixin, TimestampMixin):
    """One line of an organisation's warehouse stock — org-scoped, not
    project-scoped, since physical inventory is a shared pool drawn on by
    whichever project designs against it next (SRD FR-NET-004 extension).

    A whole-org upload REPLACES the previous snapshot (see inventory_service),
    so this is a point-in-time picture, not a ledger — it does not reserve or
    deduct stock as projects consume it. Concurrent projects both being told
    "buildable from stock" against the same units is a known limitation until
    real allocation/reservation is built.

    `match_key` is how the design/pilot engines look items up by exact type
    (e.g. "splitter:32", "connectorised_cable:8way:250") — set at ingest time
    for the categories those engines already understand. Everything else is
    matched against free-text `category`/`product_name` by the generic
    BOQ-comparison path, since most of a real stock sheet (CPE, closures,
    mounting hardware, consumables) has no structured engine consumer yet.
    """
    __tablename__ = "stock_item"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("organisation.id", ondelete="CASCADE"),
        nullable=False, index=True)

    stock_code: Mapped[str | None] = mapped_column(String(40), index=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    subcategory: Mapped[str | None] = mapped_column(String(120))
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    product_name: Mapped[str] = mapped_column(String(300), nullable=False)
    model: Mapped[str | None] = mapped_column(String(200))

    quantity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    uom: Mapped[str] = mapped_column(String(20), nullable=False, default="pcs")

    # Structured extras for categories a design engine consumes directly —
    # e.g. {"ratio": 32} for a splitter, {"kind": "8way", "ports": 8,
    # "length_m": 250} for a connectorised cable assembly. Empty for
    # everything else.
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    match_key: Mapped[str | None] = mapped_column(String(120), index=True)

    unit_cost: Mapped[float | None] = mapped_column(Numeric(12, 2))
    condition: Mapped[str | None] = mapped_column(String(40))
    warehouse: Mapped[str | None] = mapped_column(String(120))

    source_filename: Mapped[str | None] = mapped_column(String(300))
    remarks: Mapped[str | None] = mapped_column(String(500))
