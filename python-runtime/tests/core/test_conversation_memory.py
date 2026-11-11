from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.tools.conversation_memory import ConversationMemoryInput, ConversationMemoryTool


class _Context:
    project_id = "project-1"


@pytest.mark.asyncio
async def test_conversation_memory_search_and_progressive_read(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'memory.sqlite3'}")
    with engine.begin() as db:
        db.exec_driver_sql("CREATE TABLE conversations (id TEXT PRIMARY KEY, project_id TEXT, agent_id TEXT, title TEXT)")
        db.exec_driver_sql("CREATE TABLE conversation_messages (id TEXT PRIMARY KEY, conversation_id TEXT, role TEXT, content TEXT, created_at TEXT)")
        db.exec_driver_sql("INSERT INTO conversations VALUES ('conv-1','project-1','agent-1','Architecture decisions')")
        db.execute(text("INSERT INTO conversation_messages VALUES (:id,:conversation_id,:role,:content,:created_at)"), {
            "id": "msg-1", "conversation_id": "conv-1", "role": "user",
            "content": "We selected SQLite FTS5 BM25 retrieval for long term memory. " + ("x" * 1200),
            "created_at": "2026-01-01",
        })
        db.exec_driver_sql("CREATE VIRTUAL TABLE conversation_messages_fts USING fts5(message_id UNINDEXED, conversation_id UNINDEXED, agent_id UNINDEXED, project_id UNINDEXED, role UNINDEXED, content)")
        db.exec_driver_sql("INSERT INTO conversation_messages_fts VALUES ('msg-1','conv-1','agent-1','project-1','user',(SELECT content FROM conversation_messages WHERE id='msg-1'))")
    factory = sessionmaker(bind=engine)
    tool = ConversationMemoryTool(
        project_id="project-1", agent_id="agent-1", conversation_id="conv-1",
        session_factory=factory,
    )
    search = await tool.run(ConversationMemoryInput(query="SQLite FTS5 BM25"), _Context())
    assert "msg-1" in search.content
    loaded = await tool.run(ConversationMemoryInput(message_id="msg-1", max_chars=400), _Context())
    assert "We selected SQLite FTS5 BM25" in loaded.content
    assert "start_char=400" in loaded.content
