"""Persist semantic memory metadata and lessons.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-13
"""
import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("memory_entries", sa.Column("source_type", sa.String(), nullable=False, server_default="user_stated"))
    op.add_column("memory_entries", sa.Column("evidence", sa.Text(), nullable=False, server_default=""))
    op.add_column("memory_entries", sa.Column("last_used_at", sa.DateTime(), nullable=True))
    op.add_column("memory_entries", sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("memory_entries", sa.Column("expires_at", sa.DateTime(), nullable=True))
    op.add_column("memory_entries", sa.Column("status", sa.String(), nullable=False, server_default="active"))
    op.add_column("memory_entries", sa.Column("embedding", sa.JSON(), nullable=True))
    op.add_column("memory_entries", sa.Column("embedding_model", sa.String(), nullable=True))
    op.create_index(
        "ix_memory_entries_agent_status_created",
        "memory_entries",
        ["agent_id", "status", "created_at"],
    )
    op.create_table(
        "lessons",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("agent_id", sa.String(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("evidence_execution_id", sa.String(), sa.ForeignKey("executions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_lessons_agent_status_created", "lessons", ["agent_id", "status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_lessons_agent_status_created", table_name="lessons")
    op.drop_table("lessons")
    op.drop_index("ix_memory_entries_agent_status_created", table_name="memory_entries")
    op.drop_column("memory_entries", "embedding_model")
    op.drop_column("memory_entries", "embedding")
    op.drop_column("memory_entries", "status")
    op.drop_column("memory_entries", "expires_at")
    op.drop_column("memory_entries", "use_count")
    op.drop_column("memory_entries", "last_used_at")
    op.drop_column("memory_entries", "evidence")
    op.drop_column("memory_entries", "source_type")
