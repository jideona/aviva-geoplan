"""Add field-survey attributes and provenance to street.

Revision ID: 0021
Revises: 0020
"""
import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("street", sa.Column("surface", sa.String(30), nullable=False,
                                      server_default="unknown"))
    op.add_column("street", sa.Column("condition", sa.String(20), nullable=False,
                                      server_default="unknown"))
    op.add_column("street", sa.Column("access", sa.String(20), nullable=False,
                                      server_default="unknown"))
    op.add_column("street", sa.Column("width_m", sa.Numeric(6, 2)))
    op.add_column("street", sa.Column("field_notes", sa.Text()))
    op.add_column("street", sa.Column("surveyed_by", sa.String(200)))
    op.add_column("street", sa.Column("last_edited_by", sa.String(200)))
    op.add_column("street", sa.Column("assessed_at", sa.DateTime(timezone=True)))
    op.add_column("street", sa.Column("field_client_id", sa.String(64)))
    op.create_index("ix_street_surveyed_by", "street", ["surveyed_by"])
    op.create_index("ix_street_last_edited_by", "street", ["last_edited_by"])
    op.create_index("ix_street_field_client_id", "street", ["field_client_id"])


def downgrade() -> None:
    op.drop_index("ix_street_field_client_id", table_name="street")
    op.drop_index("ix_street_last_edited_by", table_name="street")
    op.drop_index("ix_street_surveyed_by", table_name="street")
    for col in ("field_client_id", "assessed_at", "last_edited_by", "surveyed_by",
                "field_notes", "width_m", "access", "condition", "surface"):
        op.drop_column("street", col)
