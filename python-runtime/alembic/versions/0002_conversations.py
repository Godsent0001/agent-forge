"""Persist conversation threads, messages and message feedback.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.String(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False, server_default="New conversation"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_conversations_project_agent_created",
        "conversations",
        ["project_id", "agent_id", "created_at"],
    )
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("conversation_id", sa.String(), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("execution_id", sa.String(), sa.ForeignKey("executions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_conversation_message_role"),
    )
    op.create_index(
        "ix_conversation_messages_conversation_created",
        "conversation_messages",
        ["conversation_id", "created_at"],
    )
    op.create_table(
        "message_feedback",
        sa.Column("message_id", sa.String(), sa.ForeignKey("conversation_messages.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("value IN (-1, 1)", name="ck_message_feedback_value"),
    )


def downgrade() -> None:
    op.drop_table("message_feedback")
    op.drop_index("ix_conversation_messages_conversation_created", table_name="conversation_messages")
    op.drop_table("conversation_messages")
    op.drop_index("ix_conversations_project_agent_created", table_name="conversations")
    op.drop_table("conversations")
