"""Index persisted conversation messages for just-in-time retrieval.

Revision ID: 0008
Revises: 0007
"""
import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    try:
        bind.exec_driver_sql(
            "CREATE VIRTUAL TABLE conversation_messages_fts USING fts5("
            "message_id UNINDEXED, conversation_id UNINDEXED, agent_id UNINDEXED, "
            "project_id UNINDEXED, role UNINDEXED, content, "
            "tokenize='unicode61 remove_diacritics 2')"
        )
    except sa.exc.OperationalError:
        # Preserve the app on SQLite builds without FTS5; retrieval tool reports unavailable.
        return
    bind.exec_driver_sql("""
        CREATE TRIGGER conversation_messages_fts_ai AFTER INSERT ON conversation_messages BEGIN
            INSERT INTO conversation_messages_fts(message_id, conversation_id, agent_id, project_id, role, content)
            SELECT new.id, c.id, c.agent_id, c.project_id, new.role, new.content
            FROM conversations c WHERE c.id = new.conversation_id AND new.role IN ('user','assistant');
        END
    """)
    bind.exec_driver_sql("""
        CREATE TRIGGER conversation_messages_fts_ad AFTER DELETE ON conversation_messages BEGIN
            DELETE FROM conversation_messages_fts WHERE message_id = old.id;
        END
    """)
    bind.exec_driver_sql("""
        CREATE TRIGGER conversation_messages_fts_au
        AFTER UPDATE OF conversation_id, role, content ON conversation_messages BEGIN
            DELETE FROM conversation_messages_fts WHERE message_id = old.id;
            INSERT INTO conversation_messages_fts(message_id, conversation_id, agent_id, project_id, role, content)
            SELECT new.id, c.id, c.agent_id, c.project_id, new.role, new.content
            FROM conversations c WHERE c.id = new.conversation_id AND new.role IN ('user','assistant');
        END
    """)
    bind.exec_driver_sql("""
        INSERT INTO conversation_messages_fts(message_id, conversation_id, agent_id, project_id, role, content)
        SELECT m.id, c.id, c.agent_id, c.project_id, m.role, m.content
        FROM conversation_messages m JOIN conversations c ON c.id = m.conversation_id
        WHERE m.role IN ('user', 'assistant')
    """)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    for trigger in ("conversation_messages_fts_ai", "conversation_messages_fts_ad", "conversation_messages_fts_au"):
        bind.exec_driver_sql(f"DROP TRIGGER IF EXISTS {trigger}")
    bind.exec_driver_sql("DROP TABLE IF EXISTS conversation_messages_fts")
