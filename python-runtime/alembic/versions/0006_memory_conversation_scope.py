"""Add conversation provenance to semantic memory entries.

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "memory_entries",
        sa.Column(
            "conversation_id",
            sa.String(),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_memory_entries_conversation_id",
        "memory_entries",
        ["conversation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_memory_entries_conversation_id", table_name="memory_entries")
    op.drop_column("memory_entries", "conversation_id")
