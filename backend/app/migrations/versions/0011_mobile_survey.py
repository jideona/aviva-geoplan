"""Mobile field survey — survey sessions, manhole assets, media attachments.

Revision ID: 0011
Revises: 0010
"""
import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "survey_session",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", sa.String(64)),
        sa.Column("surveyor_email", sa.String(200)),
        sa.Column("device", sa.String(120)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_survey_session_project", "survey_session", ["project_id"])
    op.create_index("ix_survey_session_client", "survey_session", ["client_id"])

    op.create_table(
        "manhole",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", sa.String(64)),
        sa.Column("code", sa.String(40)),
        sa.Column("manhole_type", sa.String(20), nullable=False,
                  server_default="manhole"),
        sa.Column("geom", geoalchemy2.Geometry(geometry_type="POINT", srid=4326,
                  spatial_index=True), nullable=False),
        sa.Column("gps_accuracy_m", sa.Numeric(6, 2)),
        sa.Column("condition", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("condition_notes", sa.Text),
        sa.Column("assessed_at", sa.DateTime(timezone=True)),
        sa.Column("surveyed_by", sa.String(200)),
        sa.Column("survey_session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("survey_session.id", ondelete="SET NULL")),
        sa.Column("licence_class", sa.String(30), nullable=False, server_default="owned"),
        sa.Column("verification_state", sa.String(30), nullable=False,
                  server_default="field_observed"),
        sa.Column("excluded", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_manhole_project", "manhole", ["project_id"])
    op.create_index("ix_manhole_client", "manhole", ["client_id"])

    op.create_table(
        "media_asset",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(40), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", sa.String(64)),
        sa.Column("kind", sa.String(10), nullable=False, server_default="photo"),
        sa.Column("object_key", sa.String(400), nullable=False),
        sa.Column("content_type", sa.String(80)),
        sa.Column("size_bytes", sa.Integer),
        sa.Column("caption", sa.Text),
        sa.Column("captured_lat", sa.Numeric(9, 6)),
        sa.Column("captured_lon", sa.Numeric(9, 6)),
        sa.Column("captured_at", sa.DateTime(timezone=True)),
        sa.Column("captured_by", sa.String(200)),
        sa.Column("survey_session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("survey_session.id", ondelete="SET NULL")),
        sa.Column("uploaded", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_media_project", "media_asset", ["project_id"])
    op.create_index("ix_media_entity", "media_asset", ["entity_type", "entity_id"])
    op.create_index("ix_media_client", "media_asset", ["client_id"])

    # Field-captured address on buildings.
    op.add_column("building", sa.Column("address", sa.String(300)))


def downgrade() -> None:
    op.drop_column("building", "address")
    op.drop_table("media_asset")
    op.drop_table("manhole")
    op.drop_table("survey_session")
