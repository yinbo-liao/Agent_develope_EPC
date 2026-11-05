"""p1.5 runtime: durable workflow job queue

Revision ID: p15runtime01
Revises: p1governance01
Create Date: 2026-11-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "p15runtime01"
down_revision = "p1governance01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workflow_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=128), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_id"),
    )
    op.create_index("ix_workflow_jobs_workflow_id", "workflow_jobs", ["workflow_id"])
    op.create_index("ix_workflow_jobs_status", "workflow_jobs", ["status"])
    op.create_index(
        "ix_workflow_jobs_status_available", "workflow_jobs", ["status", "available_at"]
    )
    op.create_index("ix_workflow_jobs_locked_at", "workflow_jobs", ["locked_at"])


def downgrade() -> None:
    op.drop_index("ix_workflow_jobs_locked_at", table_name="workflow_jobs")
    op.drop_index("ix_workflow_jobs_status_available", table_name="workflow_jobs")
    op.drop_index("ix_workflow_jobs_status", table_name="workflow_jobs")
    op.drop_index("ix_workflow_jobs_workflow_id", table_name="workflow_jobs")
    op.drop_table("workflow_jobs")