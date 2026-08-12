"""Field-walked survey routes (cable paths / trenches).

Revision ID: 0012
Revises: 0011
"""
import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "survey_route",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", sa.String(64)),
        sa.Column("code", sa.String(40)),
        sa.Column("route_type", sa.String(20), nullable=False,
                  server_default="cable_route"),
        sa.Column("geom", geoalchemy2.Geometry(geometry_type="LINESTRING",
                  srid=4326, spatial_index=True), nullable=False),
        sa.Column("length_m", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("point_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("avg_accuracy_m", sa.Numeric(6, 2)),
        sa.Column("notes", sa.Text),
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
    op.create_index("ix_survey_route_project", "survey_route", ["project_id"])
    op.create_index("ix_survey_route_client", "survey_route", ["client_id"])


def downgrade() -> None:
    op.drop_index("ix_survey_route_client", "survey_route")
    op.drop_index("ix_survey_route_project", "survey_route")
    op.drop_table("survey_route")
