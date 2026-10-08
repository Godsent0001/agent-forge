"""baseline schema

Revision ID: 0001
Revises:
Create Date: 2026-10-06
"""

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("parallel_execution", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("settings", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "agents",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("tool_use_schema", sa.Text(), nullable=False),
        sa.Column("memory_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("lessons_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("params", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("memory_summary", sa.Text(), nullable=False),
        sa.Column("learned_experience", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "tools",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("input_schema", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("output_schema", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("config", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.create_table(
        "executions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("root_agent_id", sa.String(), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("input_task", sa.Text(), nullable=False),
        sa.Column("final_output", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="running"),
        sa.Column("totals", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("agent_graph_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "agent_tool_links",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("agent_id", sa.String(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tool_id", sa.String(), sa.ForeignKey("tools.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("agent_id", "tool_id", name="uq_agent_tool"),
    )
    op.create_table(
        "agent_agent_links",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("parent_agent_id", sa.String(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("child_agent_id", sa.String(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.UniqueConstraint("parent_agent_id", "child_agent_id", name="uq_agent_child"),
    )
    op.create_table(
        "memory_entries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("agent_id", sa.String(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False, server_default="fact"),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_execution_id", sa.String(), sa.ForeignKey("executions.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("summarized", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "execution_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("execution_id", sa.String(), sa.ForeignKey("executions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("span_id", sa.String(), nullable=True),
        sa.Column("parent_span_id", sa.String(), nullable=True),
        sa.Column("kind", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("agent_name", sa.String(), nullable=True),
        sa.Column("tool_name", sa.String(), nullable=True),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_execution_events_execution_seq", "execution_events", ["execution_id", "seq"])
    op.create_index("ix_memory_entries_agent_created", "memory_entries", ["agent_id", "created_at"])


def downgrade() -> None:
    op.drop_table("execution_events")
    op.drop_table("memory_entries")
    op.drop_table("agent_agent_links")
    op.drop_table("agent_tool_links")
    op.drop_table("executions")
    op.drop_table("tools")
    op.drop_table("agents")
    op.drop_table("projects")
