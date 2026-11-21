from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.tools.conversation_memory import (
    ConversationFactsInput,
    ConversationFactsTool,
    ConversationMemoryInput,
    ConversationMemoryTool,
)


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


@pytest.mark.asyncio
async def test_conversation_facts_loads_multiple_files_in_one_call(monkeypatch):
    import json

    from app.core.tools import conversation_memory

    stored = {
        "architecture": {"id": "architecture", "title": "Architecture", "facts": [{"text": "Use SQLite."}]},
        "runtime": {"id": "runtime", "title": "Runtime", "facts": [{"text": "Use shared Python."}]},
    }
    monkeypatch.setattr(
        "app.services.conversation_backfill.load_fact_file",
        lambda project_id, conversation_id, file_id: stored.get(file_id),
    )
    tool = conversation_memory.ConversationFactsTool(project_id="project-1", conversation_id="conv-1")
    args = conversation_memory.ConversationFactsInput(
        action="load", file_ids=["architecture", "runtime", "architecture", "missing"]
    )
    result = await tool.run(args, SimpleNamespace())
    payload = json.loads(result.content)

    assert payload["loaded_count"] == 2
    assert [item["id"] for item in payload["files"]] == ["architecture", "runtime"]
    assert payload["missing_file_ids"] == ["missing"]


def test_conversation_facts_input_accepts_batch_and_legacy_single_id():
    from app.core.tools.conversation_memory import ConversationFactsInput

    batch = ConversationFactsInput(action="load", file_ids=["one", "two"])
    legacy = ConversationFactsInput(action="load", file_id="one")

    assert batch.file_ids == ["one", "two"]
    assert legacy.file_id == "one"


@pytest.mark.asyncio
async def test_conversation_facts_rejects_more_than_three_files():
    tool = ConversationFactsTool(project_id="project-1", conversation_id="conv-1")
    args = ConversationFactsInput(action="load", file_ids=["one", "two", "three"])
    args.file_ids.append("four")
    result = await tool.run(args, SimpleNamespace())

    assert "maximum of 3 factual files" in result.content
