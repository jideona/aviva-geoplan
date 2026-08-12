"""FDH tier.

Revision ID: 0008
Revises: 0007
"""
import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fdh",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("design_run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("design_run.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fdh_code", sa.String(40), nullable=False),
        sa.Column("point", geoalchemy2.Geometry(
            geometry_type="POINT", srid=4326, spatial_index=True), nullable=False),
        sa.Column("fat_count", sa.Integer, nullable=False),
        sa.Column("premises_count", sa.Integer, nullable=False),
        sa.Column("splitters", sa.Integer, nullable=False),
        sa.Column("splitter_ratio", sa.Integer, nullable=False),
        sa.Column("capacity", sa.Integer, nullable=False),
        sa.Column("utilisation_pct", sa.Numeric(5, 1), nullable=False),
        sa.Column("max_distribution_m", sa.Numeric(10, 1), nullable=False),
        sa.Column("road_offset_m", sa.Numeric(10, 1)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_fdh_project", "fdh", ["project_id"])
    op.create_index("ix_fdh_run", "fdh", ["design_run_id"])
    op.add_column("serving_zone", sa.Column("fdh_id", postgresql.UUID(as_uuid=True),
                                            sa.ForeignKey("fdh.id", ondelete="SET NULL")))


def downgrade() -> None:
    op.drop_column("serving_zone", "fdh_id")
    op.drop_table("fdh")
