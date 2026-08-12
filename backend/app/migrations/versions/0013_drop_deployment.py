"""Aerial vs underground drop deployment.

Per-building flag (the source of truth — per-zone setting bulk-writes it), and
a project-level aerial share assumption used only for buildings with no flag.
At share 0 every unflagged drop prices as underground.

Revision ID: 0013
Revises: 0012
"""
import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("building", sa.Column("drop_deployment", sa.String(12)))
    op.add_column("project", sa.Column(
        "aerial_drop_share", sa.Numeric(4, 3), nullable=False,
        server_default="0"))


def downgrade() -> None:
    op.drop_column("project", "aerial_drop_share")
    op.drop_column("building", "drop_deployment")
