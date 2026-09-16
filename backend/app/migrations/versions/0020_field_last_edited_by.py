"""Add last_edited_by to manhole, survey_route and building_photo, mirroring
Building.last_edited_by (0018) — standardizes "who last hand-edited this" as a
column across every field-surveyed entity rather than only Building. Only
manhole's is written today (update_condition()); survey_route/building_photo
have no edit path yet, so theirs stays null until one exists.

Revision ID: 0020
Revises: 0019
"""
import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("manhole", sa.Column("last_edited_by", sa.String(200)))
    op.create_index("ix_manhole_last_edited_by", "manhole", ["last_edited_by"])

    op.add_column("survey_route", sa.Column("last_edited_by", sa.String(200)))
    op.create_index("ix_survey_route_last_edited_by", "survey_route", ["last_edited_by"])

    op.add_column("building_photo", sa.Column("last_edited_by", sa.String(200)))
    op.create_index("ix_building_photo_last_edited_by", "building_photo", ["last_edited_by"])


def downgrade() -> None:
    op.drop_index("ix_building_photo_last_edited_by", table_name="building_photo")
    op.drop_column("building_photo", "last_edited_by")

    op.drop_index("ix_survey_route_last_edited_by", table_name="survey_route")
    op.drop_column("survey_route", "last_edited_by")

    op.drop_index("ix_manhole_last_edited_by", table_name="manhole")
    op.drop_column("manhole", "last_edited_by")
