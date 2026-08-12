"""Design runs and serving zones.

Revision ID: 0006
Revises: 0005
"""
import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "design_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engine_version", sa.String(20), nullable=False),
        sa.Column("rules", postgresql.JSONB, nullable=False),
        sa.Column("summary", postgresql.JSONB, nullable=False),
        sa.Column("warnings", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("run_by", sa.String(200)),
        sa.Column("ran_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_design_run_project", "design_run", ["project_id"])

    op.create_table(
        "serving_zone",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("design_run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("design_run.id", ondelete="CASCADE"), nullable=False),
        sa.Column("zone_code", sa.String(40), nullable=False),
        sa.Column("fat_point", geoalchemy2.Geometry(
            geometry_type="POINT", srid=4326, spatial_index=True), nullable=False),
        sa.Column("extent", geoalchemy2.Geometry(
            geometry_type="POLYGON", srid=4326, spatial_index=True)),
        sa.Column("building_count", sa.Integer, nullable=False),
        sa.Column("premises_count", sa.Integer, nullable=False),
        sa.Column("splitter_ratio", sa.Integer, nullable=False),
        sa.Column("usable_ports", sa.Integer, nullable=False),
        sa.Column("spare_ports", sa.Integer, nullable=False),
        sa.Column("utilisation_pct", sa.Numeric(5, 1), nullable=False),
        sa.Column("max_drop_m", sa.Numeric(10, 1), nullable=False),
        sa.Column("avg_drop_m", sa.Numeric(10, 1), nullable=False),
        sa.Column("road_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("street.id", ondelete="SET NULL")),
        sa.Column("road_offset_m", sa.Numeric(10, 1)),
        sa.Column("premises_assumed", sa.Boolean, nullable=False,
                  server_default=sa.false()),
        sa.Column("warnings", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("locked", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_zone_project", "serving_zone", ["project_id"])
    op.create_index("ix_zone_run", "serving_zone", ["design_run_id"])

    # Which zone serves each building.
    op.add_column("building", sa.Column("serving_zone_id",
                                        postgresql.UUID(as_uuid=True),
                                        sa.ForeignKey("serving_zone.id",
                                                      ondelete="SET NULL")))
    op.create_index("ix_building_zone", "building", ["serving_zone_id"])


def downgrade() -> None:
    op.drop_index("ix_building_zone", "building")
    op.drop_column("building", "serving_zone_id")
    op.drop_table("serving_zone")
    op.drop_table("design_run")
