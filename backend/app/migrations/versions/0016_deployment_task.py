"""Deployment task tracking — project-management layer (phase 1 of the
GeoPlan_Deployment_PM_Proposal.docx plan; replaces the "Deployment plan"
monday.com board).

Revision ID: 0016
Revises: 0015
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deployment_task",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("project.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("area", sa.String(20), nullable=False, server_default="other"),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default="not_started"),
        sa.Column("assignee_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("app_user.id", ondelete="SET NULL")),
        sa.Column("start_date", sa.Date()),
        sa.Column("end_date", sa.Date()),
        sa.Column("updates", sa.Text()),
        sa.Column("issues", sa.Text()),
        sa.Column("entity_type", sa.String(40)),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("app_user.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_deployment_task_project_id", "deployment_task", ["project_id"])
    op.create_index("ix_deployment_task_area", "deployment_task", ["area"])
    op.create_index("ix_deployment_task_status", "deployment_task", ["status"])
    op.create_index("ix_deployment_task_assignee_id", "deployment_task", ["assignee_id"])
    op.create_index("ix_deployment_task_entity_type", "deployment_task", ["entity_type"])
    op.create_index("ix_deployment_task_entity_id", "deployment_task", ["entity_id"])


def downgrade() -> None:
    op.drop_index("ix_deployment_task_entity_id", "deployment_task")
    op.drop_index("ix_deployment_task_entity_type", "deployment_task")
    op.drop_index("ix_deployment_task_assignee_id", "deployment_task")
    op.drop_index("ix_deployment_task_status", "deployment_task")
    op.drop_index("ix_deployment_task_area", "deployment_task")
    op.drop_index("ix_deployment_task_project_id", "deployment_task")
    op.drop_table("deployment_task")
