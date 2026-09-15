"""Add Building.condition (field-assessed excellent/good/fair/poor, separate
from Manhole's condition vocabulary) and a building_manhole_link join table
for the "Associated Assets" section of the redesigned Update Building screen.

Revision ID: 0019
Revises: 0018
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("building", sa.Column("condition", sa.String(20)))

    op.create_table(
        "building_manhole_link",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("building_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("building.id", ondelete="CASCADE"), nullable=False),
        sa.Column("manhole_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("manhole.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", sa.String(200)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("building_id", "manhole_id", name="uq_building_manhole_link"),
    )
    op.create_index("ix_building_manhole_link_building_id", "building_manhole_link", ["building_id"])
    op.create_index("ix_building_manhole_link_manhole_id", "building_manhole_link", ["manhole_id"])


def downgrade() -> None:
    op.drop_index("ix_building_manhole_link_manhole_id", table_name="building_manhole_link")
    op.drop_index("ix_building_manhole_link_building_id", table_name="building_manhole_link")
    op.drop_table("building_manhole_link")
    op.drop_column("building", "condition")
