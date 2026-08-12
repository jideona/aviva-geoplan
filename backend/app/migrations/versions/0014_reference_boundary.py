"""Cached ward/district boundaries from public reference sources (GRID3
ward FeatureServer, OSM admin_level=7 district relations). Global cache, not
project-scoped — fetched once per name, then reused forever until a caller
explicitly refreshes it.

Revision ID: 0014
Revises: 0013
"""
import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reference_boundary",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("name_normalized", sa.String(150), nullable=False),
        sa.Column("state_code", sa.String(10), nullable=False),
        sa.Column("lga_name", sa.String(100)),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("source_ref", sa.String(200), nullable=False),
        sa.Column("geom", geoalchemy2.Geometry(
            geometry_type="MULTIPOLYGON", srid=4326, spatial_index=True),
            nullable=False),
        sa.Column("area_sqkm", sa.Numeric(12, 4), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_reference_boundary_name", "reference_boundary",
                     ["name_normalized"])
    # One cached row per exact upstream record — re-fetching the same ward
    # or relation updates in place rather than piling up duplicates.
    op.create_index("ux_reference_boundary_source", "reference_boundary",
                     ["source", "source_ref"], unique=True)


def downgrade() -> None:
    op.drop_index("ux_reference_boundary_source", "reference_boundary")
    op.drop_index("ix_reference_boundary_name", "reference_boundary")
    op.drop_table("reference_boundary")
