"""Estate and compound perimeters.

Revision ID: 0007
Revises: 0006
"""
import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "parcel",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parcel_code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("raw_name", sa.String(400)),
        sa.Column("survey_code", sa.String(20)),
        sa.Column("geom", geoalchemy2.Geometry(
            geometry_type="POLYGON", srid=4326, spatial_index=True), nullable=False),
        sa.Column("area_sqm", sa.Numeric(14, 2), nullable=False),
        sa.Column("perimeter_m", sa.Numeric(12, 2), nullable=False),
        sa.Column("access_point", geoalchemy2.Geometry(
            geometry_type="POINT", srid=4326, spatial_index=True)),
        sa.Column("building_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("marker_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("declared_units", sa.Integer),
        sa.Column("observed_units", sa.Integer),
        sa.Column("street_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("street.id", ondelete="SET NULL")),
        sa.Column("data_source_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("data_source.id", ondelete="SET NULL")),
        sa.Column("licence_class", sa.String(30), nullable=False,
                  server_default="owned"),
        sa.Column("verification_state", sa.String(30), nullable=False,
                  server_default="field_observed"),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_parcel_project", "parcel", ["project_id"])
    op.create_index("ix_parcel_survey_code", "parcel", ["survey_code"])

    op.add_column("building", sa.Column("parcel_id", postgresql.UUID(as_uuid=True),
                                        sa.ForeignKey("parcel.id",
                                                      ondelete="SET NULL")))
    op.create_index("ix_building_parcel", "building", ["parcel_id"])


def downgrade() -> None:
    op.drop_index("ix_building_parcel", "building")
    op.drop_column("building", "parcel_id")
    op.drop_table("parcel")
