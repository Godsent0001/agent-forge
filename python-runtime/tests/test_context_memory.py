"""Regression tests for conversation continuity across many turns and chats."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import sessionmaker

from app import models
from app.core.memory.compaction import history_budget_chars
from app.services import context_memory, task_memory
from app.services.context_memory import (
    SUMMARY_KEY,
    build_conversation_context,
    compact_conversation_context,
)

_T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _Chat:
    def __init__(self, db, monkeypatch, tmp_path):
        self.db = db
        self.clock = 0
        monkeypatch.setattr(task_memory, "project_dir", lambda _project_id: tmp_path)
        self.project = models.Project(name="Context memory tests")
        db.add(self.project)
        db.flush()
        self.agent = models.Agent(project_id=self.project.id, name="A", provider="fake", model="fake/demo")
        db.add(self.agent)
        db.flush()
        self.conversation = self.new_conversation()
        self.factory = sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False)

    def new_conversation(self):
        conversation = models.Conversation(project_id=self.project.id, agent_id=self.agent.id)
        self.db.add(conversation)
        self.db.commit()
        return conversation

    def say(self, role, content, conversation=None):
        self.clock += 1
        message = models.ConversationMessage(
            conversation_id=(conversation or self.conversation).id, role=role, content=content,
            created_at=_T0 + timedelta(minutes=self.clock),
        )
        self.db.add(message)
        self.db.commit()
        return message

    def ask(self, content, conversation=None):
        """Persist a user turn the way the API does and return its task id."""
        self.say("user", content, conversation)
        task_id, _ = task_memory.prepare_task_state(self.db, conversation or self.conversation, content)
        return task_id

    async def compact(self, task_id, current, budget_chars, summarize=None, conversation=None):
        result = await compact_conversation_context(
            task_id, (conversation or self.conversation).id, current,
            budget_chars=budget_chars, summarize_fn=summarize, session_factory=self.factory,
        )
        self.db.expire_all()
        return result


@pytest.fixture()
def chat(db_session, monkeypatch, tmp_path):
    return _Chat(db_session, monkeypatch, tmp_path)


@pytest.mark.asyncio
async def test_ten_turn_chat_keeps_every_turn_verbatim(chat):
    """The original bug: turn 5 onwards lost everything older than four exchanges."""
    task_id = chat.ask("I'm building CrumbTrack. The database is Postgres 16 on port 5433.")
    chat.say("assistant", "Scaffolded CrumbTrack against Postgres 16 on port 5433.")
    chat.ask("What about Redis for caching?")
    chat.say("assistant", "Redis fits; I suggest a 5 minute TTL.")
    chat.ask("ok go with that")
    chat.say("assistant", "Done. Configured Redis with a 300s TTL.")
    for index in range(7):
        chat.ask(f"filler question {index}")
        chat.say("assistant", f"filler answer {index}")
    question = "What TTL did you set for Redis?"
    task_id = chat.ask(question)

    history, summary = await chat.compact(task_id, question, history_budget_chars(32_000))

    assert summary == ""  # nothing needed summarising: it all fits
    assert len(history) == 20
    assert history[0]["content"].endswith("port 5433.")
    assert any("300s TTL" in message["content"] for message in history)
    assert history[-1] == {"role": "assistant", "content": "filler answer 6"}


@pytest.mark.asyncio
async def test_overflow_is_summarised_once_and_the_cursor_advances(chat):
    calls = []

    async def summarize(messages):
        calls.append(messages[1]["content"])
        return f"SUMMARY v{len(calls)}"

    task_id = None
    for index in range(12):
        task_id = chat.ask(f"question {index} " + "q" * 600)
        chat.say("assistant", f"answer {index} " + "a" * 600)
    current = "latest question"
    task_id = chat.ask(current)

    history, summary = await chat.compact(task_id, current, 8_000, summarize)
    assert summary == "SUMMARY v1" and len(calls) == 1
    assert "question 0" in calls[0] and "(none yet)" in calls[0]
    assert history[0]["role"] == "user"
    assert sum(len(m["content"]) for m in history) <= 8_000
    kept_first = history[0]["content"][:12]

    # Same state again: the summary is reused, no second model call.
    history_again, summary_again = await chat.compact(task_id, current, 8_000, summarize)
    assert (summary_again, len(calls)) == ("SUMMARY v1", 1)
    assert history_again[0]["content"][:12] == kept_first

    # The request path sees the same stored summary and only uncovered messages.
    served, served_summary, available = build_conversation_context(
        chat.db, task_id, chat.conversation.id, current
    )
    assert available and served_summary == "SUMMARY v1"
    assert served[0]["content"][:12] == kept_first

    # More turns overflow again: the next call folds in the previous summary.
    chat.say("assistant", "latest answer")
    for index in range(12, 20):
        task_id = chat.ask(f"question {index} " + "q" * 600)
        chat.say("assistant", f"answer {index} " + "a" * 600)
    task_id = chat.ask("final")
    _, summary = await chat.compact(task_id, "final", 8_000, summarize)
    assert summary == "SUMMARY v2"
    assert calls[1].startswith("EXISTING SUMMARY:\nSUMMARY v1")
    assert "question 0 " not in calls[1]  # already covered; never re-summarised


@pytest.mark.asyncio
async def test_summary_survives_other_task_state_writers(chat, monkeypatch):
    for index in range(12):
        task_id = chat.ask(f"question {index} " + "q" * 600)
        chat.say("assistant", f"answer {index} " + "a" * 600)
    task_id = chat.ask("now")

    async def summarize(_messages):
        return "KEPT"

    await chat.compact(task_id, "now", 8_000, summarize)
    monkeypatch.setattr("app.db.SessionLocal", chat.factory)
    chat.db.add(models.Execution(
        id="exec-1", project_id=chat.project.id, root_agent_id=chat.agent.id,
        input_task="now", status="completed",
    ))
    chat.db.commit()
    task_memory.record_task_execution_result(task_id, "exec-1", "completed", "did things")
    chat.db.expire_all()
    state = chat.db.get(models.TaskState, task_id).state_json
    assert state[SUMMARY_KEY]["summary"] == "KEPT"
    assert "constraints" in state  # compaction did not clobber the rest of the document


@pytest.mark.asyncio
async def test_editing_a_summarised_message_rebuilds_the_summary(chat):
    first = None
    for index in range(12):
        message_task = chat.ask(f"question {index} " + "q" * 600)
        first = first or chat.db.query(models.ConversationMessage).first()
        chat.say("assistant", f"answer {index} " + "a" * 600)
    task_id = chat.ask("now")
    seen = []

    async def summarize(messages):
        seen.append(messages[1]["content"])
        return "S"

    await chat.compact(task_id, "now", 8_000, summarize)
    assert message_task == task_id
    chat.db.delete(first)  # the UI's edit flow removes the edited message and what followed
    chat.db.commit()

    _, summary = await chat.compact(task_id, "now", 8_000, summarize)
    assert summary == "S" and len(seen) == 2
    assert "(none yet)" in seen[1]  # stale summary discarded, not extended


@pytest.mark.asyncio
async def test_resumed_workstream_carries_the_previous_chat_into_the_new_one(chat):
    task_id = chat.ask("Build the payment engine. Settlement currency is NGN.")
    chat.say("assistant", "Understood: NGN settlement.")
    second = chat.new_conversation()
    resumed = chat.ask(f"Resume task: {task_id[:8]}", second)
    assert resumed == task_id
    chat.say("assistant", "Resumed.", second)
    current = "Which currency did we agree on?"
    chat.ask(current, second)

    history, _ = await chat.compact(task_id, current, history_budget_chars(32_000), conversation=second)

    assert history[0]["content"] == "Build the payment engine. Settlement currency is NGN."
    assert history[1]["content"] == "Understood: NGN settlement."


@pytest.mark.asyncio
async def test_without_a_model_overflow_still_leaves_a_trace(chat):
    task_id = chat.ask("The deploy target is fly.io region lhr. " + "x" * 900)
    chat.say("assistant", "Deployed build 4812 to lhr. " + "y" * 900)
    for index in range(10):
        chat.ask(f"q{index} " + "q" * 700)
        chat.say("assistant", f"a{index} " + "a" * 700)
    task_id = chat.ask("now")

    _, summary = await chat.compact(task_id, "now", 8_000, None)

    assert "fly.io region lhr" in summary and "4812" in summary


def test_summary_written_by_the_first_implementation_is_carried_over(chat):
    task_id = chat.ask("first")
    covered = chat.say("assistant", "reply one")
    chat.ask("second")
    chat.say("assistant", "reply two")
    task = chat.db.get(models.TaskState, task_id)
    task.state_json = {**task.state_json, SUMMARY_KEY: {
        "pinned": ["- must use SQLite"], "progress": [], "archived": 0,
        "cursors": {chat.conversation.id: {"last_id": covered.id, "count": 2}},
    }}
    chat.db.commit()

    history, summary, _ = build_conversation_context(chat.db, task_id, chat.conversation.id, "third")

    assert "must use SQLite" in summary
    assert [m["content"] for m in history] == ["second", "reply two"]


def test_load_is_bounded_for_very_long_unsummarised_chats(chat, monkeypatch):
    monkeypatch.setattr(context_memory, "_LOAD_MAX_CHARS", 5_000)
    task_id = None
    for index in range(30):
        task_id = chat.ask(f"q{index} " + "q" * 500)
    history, _, _ = build_conversation_context(chat.db, task_id, chat.conversation.id, "now")
    assert sum(len(m["content"]) for m in history) <= 6_000
