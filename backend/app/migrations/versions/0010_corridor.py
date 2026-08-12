"""Drop corridors — traced footpaths, pathways and fence lines for drop routing.

Revision ID: 0010
Revises: 0009
"""
import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "corridor",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("corridor_type", sa.String(20), nullable=False,
                  server_default="footpath"),
        sa.Column("geom", geoalchemy2.Geometry(
            geometry_type="LINESTRING", srid=4326, spatial_index=True),
            nullable=False),
        sa.Column("length_m", sa.Numeric(12, 2), nullable=False,
                  server_default="0"),
        sa.Column("capture_source", sa.String(30), nullable=False),
        sa.Column("licence_class", sa.String(30), nullable=False,
                  server_default="desk_reference_restricted"),
        sa.Column("verification_state", sa.String(30), nullable=False,
                  server_default="desk_verified"),
        sa.Column("commercial_ready", sa.Boolean, nullable=False,
                  server_default=sa.false()),
        sa.Column("created_by", sa.String(200)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_corridor_project", "corridor", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_corridor_project", "corridor")
    op.drop_table("corridor")
