"""Track who last hand-edited a building, so the office map and field-activity
feed can show "modified in the field" with an attributed surveyor rather than
only a bare updated_at timestamp.

Revision ID: 0018
Revises: 0017
"""
import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("building", sa.Column("last_edited_by", sa.String(200)))
    op.create_index("ix_building_last_edited_by", "building", ["last_edited_by"])


def downgrade() -> None:
    op.drop_index("ix_building_last_edited_by", table_name="building")
    op.drop_column("building", "last_edited_by")
