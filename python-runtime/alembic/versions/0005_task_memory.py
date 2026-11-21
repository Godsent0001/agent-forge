"""Durable conversation-scoped task memory.

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_states",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("conversation_id", sa.String(), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.String(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("original_objective", sa.Text(), nullable=False),
        sa.Column("current_instruction", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("state_json", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_task_states_conversation_status",
        "task_states",
        ["conversation_id", "status", "updated_at"],
    )
    op.create_index(
        "ix_task_states_project_updated",
        "task_states",
        ["project_id", "updated_at"],
    )
    op.create_table(
        "task_state_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("task_state_id", sa.String(), sa.ForeignKey("task_states.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_execution_id", sa.String(), sa.ForeignKey("executions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_task_state_events_task_created",
        "task_state_events",
        ["task_state_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_task_state_events_task_created", table_name="task_state_events")
    op.drop_table("task_state_events")
    op.drop_index("ix_task_states_project_updated", table_name="task_states")
    op.drop_index("ix_task_states_conversation_status", table_name="task_states")
    op.drop_table("task_states")
