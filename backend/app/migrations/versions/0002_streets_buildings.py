"""Streets and canonical buildings.

Revision ID: 0002
Revises: 0001
"""
import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "street",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("street_code", sa.String(30), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("geom", geoalchemy2.Geometry(
            geometry_type="MULTILINESTRING", srid=4326, spatial_index=True),
            nullable=False),
        sa.Column("length_m", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("road_class", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("data_source_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("data_source.id", ondelete="SET NULL")),
        sa.Column("external_id", sa.String(200)),
        sa.Column("licence_class", sa.String(30), nullable=False, server_default="owned"),
        sa.Column("verification_state", sa.String(30), nullable=False,
                  server_default="imported"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("project_id", "street_code", name="uq_street_code"),
    )
    op.create_index("ix_street_project", "street", ["project_id"])
    op.create_index("ix_street_external", "street", ["external_id"])

    op.create_table(
        "building",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("street_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("street.id", ondelete="SET NULL")),
        sa.Column("building_code", sa.String(40)),
        sa.Column("geom", geoalchemy2.Geometry(
            geometry_type="POLYGON", srid=4326, spatial_index=True), nullable=False),
        sa.Column("centroid", geoalchemy2.Geometry(
            geometry_type="POINT", srid=4326, spatial_index=True), nullable=False),
        sa.Column("footprint_area_sqm", sa.Numeric(12, 2), nullable=False),
        sa.Column("perimeter_m", sa.Numeric(12, 2), nullable=False),
        sa.Column("building_type", sa.String(30), nullable=False,
                  server_default="unclassified"),
        sa.Column("use_type", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("name", sa.String(200)),
        sa.Column("floors_reported", sa.Integer),
        sa.Column("height_measured_m", sa.Numeric(8, 2)),
        sa.Column("height_modelled_m", sa.Numeric(8, 2)),
        sa.Column("height_modelled_cells", sa.Integer),
        sa.Column("height_modelled_stddev", sa.Numeric(8, 2)),
        sa.Column("height_modelled_year", sa.Integer),
        sa.Column("units_surveyed", sa.Integer),
        sa.Column("premises_estimated", sa.Integer),
        sa.Column("premises_estimate_low", sa.Integer),
        sa.Column("premises_estimate_high", sa.Integer),
        sa.Column("estimation_model_version", sa.String(40)),
        sa.Column("data_source_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("data_source.id", ondelete="SET NULL")),
        sa.Column("external_id", sa.String(200)),
        sa.Column("source_dataset", sa.String(80)),
        sa.Column("source_update_date", sa.Date),
        sa.Column("licence_class", sa.String(30), nullable=False,
                  server_default="proprietary_restricted"),
        sa.Column("detection_confidence", sa.Numeric(5, 4)),
        sa.Column("verification_state", sa.String(30), nullable=False,
                  server_default="imported"),
        sa.Column("survey_status", sa.String(30), nullable=False,
                  server_default="not_surveyed"),
        sa.Column("notes", sa.Text),
        sa.Column("source_attributes", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("project_id", "building_code", name="uq_building_code"),
    )
    op.create_index("ix_building_project", "building", ["project_id"])
    op.create_index("ix_building_street", "building", ["street_id"])
    op.create_index("ix_building_external", "building", ["external_id"])
    op.create_index("ix_building_verification", "building", ["verification_state"])
    # Re-import matches on this pair (SRD FR-IMP-023).
    op.create_index("ix_building_project_external", "building",
                    ["project_id", "external_id"])


def downgrade() -> None:
    op.drop_table("building")
    op.drop_table("street")
