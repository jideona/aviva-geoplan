"""Building exclusion (non-serviceable, reversible).

Revision ID: 0009
Revises: 0008
"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("building", sa.Column("excluded", sa.Boolean, nullable=False,
                                        server_default=sa.false()))
    op.add_column("building", sa.Column("excluded_reason", sa.String(200)))
    op.create_index("ix_building_excluded", "building", ["excluded"])


def downgrade() -> None:
    op.drop_index("ix_building_excluded", "building")
    op.drop_column("building", "excluded_reason")
    op.drop_column("building", "excluded")
