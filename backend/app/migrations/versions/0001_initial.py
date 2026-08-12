"""Initial schema: organisations, users, projects, boundaries, provenance, audit.

Revision ID: 0001
Revises:
"""
import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "organisation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False, unique=True),
        sa.Column("country", sa.String(2), nullable=False, server_default="NG"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "app_user",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organisation.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("roles", postgresql.ARRAY(sa.String(50)), nullable=False,
                  server_default="{}"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_app_user_email", "app_user", ["email"])
    op.create_index("ix_app_user_org", "app_user", ["organisation_id"])

    op.create_table(
        "project",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organisation.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("client", sa.String(200)),
        sa.Column("country", sa.String(2), nullable=False, server_default="NG"),
        sa.Column("state", sa.String(100)),
        sa.Column("city", sa.String(100)),
        sa.Column("district", sa.String(100), nullable=False),
        sa.Column("code_prefix", sa.String(3), nullable=False),
        sa.Column("metric_crs_epsg", sa.Integer, nullable=False, server_default="32632"),
        sa.Column("project_type", sa.String(30), nullable=False, server_default="ftth"),
        sa.Column("network_technology", sa.String(20), nullable=False,
                  server_default="xgs_pon"),
        sa.Column("design_capacity", sa.Integer),
        sa.Column("expected_takeup_rate", sa.Numeric(5, 4)),
        sa.Column("design_horizon", sa.Date),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_project_org", "project", ["organisation_id"])

    op.create_table(
        "project_boundary",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("geom", geoalchemy2.Geometry(
            geometry_type="MULTIPOLYGON", srid=4326, spatial_index=True), nullable=False),
        sa.Column("area_sqkm", sa.Numeric(12, 4), nullable=False),
        sa.Column("source_filename", sa.String(255), nullable=False),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("verification_state", sa.String(30), nullable=False,
                  server_default="imported"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_boundary_project", "project_boundary", ["project_id"])

    op.create_table(
        "data_source",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("licence", sa.String(120)),
        sa.Column("licence_class", sa.String(30), nullable=False, server_default="owned"),
        sa.Column("attribution_text", sa.Text),
        sa.Column("source_date", sa.Date),
        sa.Column("admitted_role", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "provenance_record",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_type", sa.String(60), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("data_source_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("data_source.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4)),
        sa.Column("external_id", sa.String(200)),
        sa.Column("imported_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_prov_entity", "provenance_record", ["entity_type", "entity_id"])
    op.create_index("ix_prov_external", "provenance_record", ["external_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("actor_email", sa.String(320)),
        sa.Column("entity_type", sa.String(60), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True)),
        sa.Column("changes", postgresql.JSONB),
        sa.Column("request_id", sa.String(64)),
    )
    op.create_index("ix_audit_occurred", "audit_log", ["occurred_at"])
    op.create_index("ix_audit_entity", "audit_log", ["entity_type", "entity_id"])
    op.create_index("ix_audit_project", "audit_log", ["project_id"])

    # Audit rows are append-only. Enforced in the database, not only in code.
    op.execute("""
        CREATE OR REPLACE FUNCTION audit_log_is_append_only()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only';
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER audit_log_no_update_delete
        BEFORE UPDATE OR DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION audit_log_is_append_only();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update_delete ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_is_append_only()")
    op.drop_table("audit_log")
    op.drop_table("provenance_record")
    op.drop_table("data_source")
    op.drop_table("project_boundary")
    op.drop_table("project")
    op.drop_table("app_user")
    op.drop_table("organisation")
