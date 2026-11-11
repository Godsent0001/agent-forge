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

_FOREIGN_KEY = "fk_memory_entries_conversation_id_conversations"
_INDEX = "ix_memory_entries_conversation_id"


def upgrade() -> None:
    # SQLite's direct ALTER TABLE ADD COLUMN path is fragile for a REFERENCES
    # column across supported SQLite builds. Rebuild the table transactionally
    # through Alembic's batch implementation so the FK and index are created
    # consistently while preserving all existing memory rows and indexes.
    with op.batch_alter_table("memory_entries", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("conversation_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            _FOREIGN_KEY,
            "conversations",
            ["conversation_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(_INDEX, ["conversation_id"])


def downgrade() -> None:
    with op.batch_alter_table("memory_entries", recreate="always") as batch_op:
        batch_op.drop_index(_INDEX)
        batch_op.drop_constraint(_FOREIGN_KEY, type_="foreignkey")
        batch_op.drop_column("conversation_id")
