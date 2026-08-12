"""Quick building photo capture — standalone geotagged point, photo attached
via the existing media_asset pipeline (entity_type='building_photo').

Revision ID: 0017
Revises: 0016
"""
import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "building_photo",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", sa.String(64)),
        sa.Column("geom", geoalchemy2.Geometry(geometry_type="POINT", srid=4326,
                  spatial_index=True), nullable=False),
        sa.Column("gps_accuracy_m", sa.Numeric(6, 2)),
        sa.Column("surveyed_by", sa.String(200)),
        sa.Column("licence_class", sa.String(30), nullable=False, server_default="owned"),
        sa.Column("verification_state", sa.String(30), nullable=False,
                  server_default="field_observed"),
        sa.Column("excluded", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_building_photo_project", "building_photo", ["project_id"])
    op.create_index("ix_building_photo_client", "building_photo", ["client_id"])


def downgrade() -> None:
    op.drop_table("building_photo")
