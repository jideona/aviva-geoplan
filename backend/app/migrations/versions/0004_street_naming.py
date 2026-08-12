"""Street name sourcing and commercial clearance.

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("street", sa.Column("name_source", sa.String(30)))
    op.add_column("street", sa.Column("name_recorded_by", sa.String(200)))
    op.add_column("street", sa.Column("name_evidence_key", sa.String(500)))
    op.add_column("street", sa.Column("name_note", sa.Text))
    op.create_index("ix_street_name_source", "street", ["name_source"])
    # Names already present came in with the OSM import.
    op.execute("UPDATE street SET name_source='open_data' "
               "WHERE name IS NOT NULL AND name_source IS NULL")


def downgrade() -> None:
    op.drop_index("ix_street_name_source", "street")
    op.drop_column("street", "name_note")
    op.drop_column("street", "name_evidence_key")
    op.drop_column("street", "name_recorded_by")
    op.drop_column("street", "name_source")
