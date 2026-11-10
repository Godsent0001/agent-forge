"""Create FTS5 index for long-term memory entries when SQLite supports it.

Revision ID: 0007
Revises: 0006
"""
import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    try:
        bind.exec_driver_sql(
            "CREATE VIRTUAL TABLE memory_entries_fts USING fts5("
            "memory_id UNINDEXED, agent_id UNINDEXED, conversation_id UNINDEXED, content, "
            "tokenize='unicode61 remove_diacritics 2')"
        )
        bind.exec_driver_sql("""
            CREATE TRIGGER memory_entries_fts_ai AFTER INSERT ON memory_entries BEGIN
                INSERT INTO memory_entries_fts(memory_id, agent_id, conversation_id, content)
                VALUES (new.id, new.agent_id, new.conversation_id, new.content);
            END
        """)
        bind.exec_driver_sql("""
            CREATE TRIGGER memory_entries_fts_ad AFTER DELETE ON memory_entries BEGIN
                DELETE FROM memory_entries_fts WHERE memory_id = old.id;
            END
        """)
        bind.exec_driver_sql("""
            CREATE TRIGGER memory_entries_fts_au
            AFTER UPDATE OF content, agent_id, conversation_id ON memory_entries BEGIN
                DELETE FROM memory_entries_fts WHERE memory_id = old.id;
                INSERT INTO memory_entries_fts(memory_id, agent_id, conversation_id, content)
                VALUES (new.id, new.agent_id, new.conversation_id, new.content);
            END
        """)
        bind.exec_driver_sql(
            "INSERT INTO memory_entries_fts(memory_id, agent_id, conversation_id, content) "
            "SELECT id, agent_id, conversation_id, content FROM memory_entries"
        )
    except sa.exc.OperationalError:
        # FTS5 is optional in some SQLite builds; the store keeps its lexical fallback.
        return


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    for trigger in ("memory_entries_fts_ai", "memory_entries_fts_ad", "memory_entries_fts_au"):
        bind.exec_driver_sql(f"DROP TRIGGER IF EXISTS {trigger}")
    bind.exec_driver_sql("DROP TABLE IF EXISTS memory_entries_fts")
