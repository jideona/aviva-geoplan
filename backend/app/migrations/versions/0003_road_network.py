"""Unnamed roads and street assignment provenance.

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Road geometry in Wuye is largely complete; names largely are not.
    # Importing only named roads would discard 59 of 70 km of network.
    op.alter_column("street", "name", existing_type=sa.String(200), nullable=True)
    op.add_column("street", sa.Column("name_status", sa.String(20), nullable=False,
                                      server_default="unnamed"))
    op.add_column("street", sa.Column("needs_field_name", sa.Boolean, nullable=False,
                                      server_default=sa.true()))
    op.execute("UPDATE street SET name_status='named', needs_field_name=false "
               "WHERE name IS NOT NULL")

    op.add_column("building", sa.Column("street_assignment_confidence",
                                        sa.Numeric(5, 3)))
    op.add_column("building", sa.Column("street_assignment_reason", sa.String(200)))
    op.add_column("building", sa.Column("street_assignment_distance_m",
                                        sa.Numeric(10, 2)))
    op.create_index("ix_building_assignment_conf", "building",
                    ["street_assignment_confidence"])


def downgrade() -> None:
    op.drop_index("ix_building_assignment_conf", "building")
    op.drop_column("building", "street_assignment_distance_m")
    op.drop_column("building", "street_assignment_reason")
    op.drop_column("building", "street_assignment_confidence")
    op.drop_column("street", "needs_field_name")
    op.drop_column("street", "name_status")
    op.execute("UPDATE street SET name='(unnamed)' WHERE name IS NULL")
    op.alter_column("street", "name", existing_type=sa.String(200), nullable=False)
