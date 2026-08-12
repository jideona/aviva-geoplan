"""Warehouse stock snapshot, org-scoped — feeds the design engine's
"buildable from stock vs needs purchase" comparison (extends SRD FR-NET-004
beyond splitters/connectorised cable to the whole SOM/BOQ).

Revision ID: 0015
Revises: 0014
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stock_item",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organisation.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("stock_code", sa.String(40)),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("subcategory", sa.String(120)),
        sa.Column("manufacturer", sa.String(120)),
        sa.Column("product_name", sa.String(300), nullable=False),
        sa.Column("model", sa.String(200)),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("uom", sa.String(20), nullable=False, server_default="pcs"),
        sa.Column("attributes", postgresql.JSONB, nullable=False,
                  server_default="{}"),
        sa.Column("match_key", sa.String(120)),
        sa.Column("unit_cost", sa.Numeric(12, 2)),
        sa.Column("condition", sa.String(40)),
        sa.Column("warehouse", sa.String(120)),
        sa.Column("source_filename", sa.String(300)),
        sa.Column("remarks", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_stock_item_organisation_id", "stock_item", ["organisation_id"])
    op.create_index("ix_stock_item_stock_code", "stock_item", ["stock_code"])
    op.create_index("ix_stock_item_category", "stock_item", ["category"])
    op.create_index("ix_stock_item_match_key", "stock_item", ["match_key"])


def downgrade() -> None:
    op.drop_index("ix_stock_item_match_key", "stock_item")
    op.drop_index("ix_stock_item_category", "stock_item")
    op.drop_index("ix_stock_item_stock_code", "stock_item")
    op.drop_index("ix_stock_item_organisation_id", "stock_item")
    op.drop_table("stock_item")
