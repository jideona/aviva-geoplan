"""Recorded street names and premises observations from field survey.

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recorded_street",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("recorded_length_m", sa.Numeric(10, 1)),
        sa.Column("survey_date", sa.Date),
        sa.Column("surveyor", sa.String(200)),
        sa.Column("source_file", sa.String(255)),
        sa.Column("matched_street_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("street.id", ondelete="SET NULL")),
        sa.Column("match_status", sa.String(20), nullable=False,
                  server_default="unmatched"),
        sa.Column("matched_by", sa.String(200)),
        sa.Column("length_delta_pct", sa.Numeric(8, 2)),
        sa.Column("note", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_recorded_street_project", "recorded_street", ["project_id"])
    op.create_index("ix_recorded_street_status", "recorded_street", ["match_status"])

    op.create_table(
        "premises_observation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("estate_name", sa.String(255), nullable=False),
        sa.Column("building_count", sa.Integer, nullable=False),
        sa.Column("units_per_building", sa.Integer, nullable=False),
        sa.Column("typology", sa.String(20), nullable=False,
                  server_default="unknown"),
        sa.Column("street_hint", sa.String(200)),
        sa.Column("building_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("building.id", ondelete="SET NULL")),
        sa.Column("survey_date", sa.Date),
        sa.Column("surveyor", sa.String(200)),
        sa.Column("source_file", sa.String(255)),
        sa.Column("verification_state", sa.String(30), nullable=False,
                  server_default="field_observed"),
        sa.Column("note", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_premises_obs_project", "premises_observation", ["project_id"])
    op.create_index("ix_premises_obs_typology", "premises_observation", ["typology"])


def downgrade() -> None:
    op.drop_table("premises_observation")
    op.drop_table("recorded_street")
