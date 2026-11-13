"""The runner must deliver memory to the model intact and fit history to the model."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import sessionmaker

from app import models
from app.contracts.graph import AgentSpec
from app.contracts.run import BudgetSpec
from app.core.budget import BudgetTracker
from app.core.llm.fake import FakeLLM
from app.core.llm.types import LLMTurn
from app.core.runner import RunnerCore
from app.services import task_memory


async def _emit(event):
    return SimpleNamespace(seq=0, span_id="span", **{})


def _spec() -> AgentSpec:
    return AgentSpec(id="agent", name="Agent", provider="fake", model="fake/demo")


@pytest.mark.asyncio
async def test_system_prompt_and_user_turns_reach_the_model_unclipped(monkeypatch):
    monkeypatch.setattr("app.core.runner.get_context_window", lambda _model: 200_000)
    fake = FakeLLM([LLMTurn(text="ok")])
    system = "role " + "i" * 9_000 + "\n<conversation_summary>\nRedis TTL is 300s\n</conversation_summary>"
    tool_output = "t" * 9_000 + " full result saved at .results/call-1.txt"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": "u" * 9_000 + " END OF USER MESSAGE"},
        {"role": "tool", "tool_call_id": "call-1", "content": tool_output},
    ]

    await RunnerCore(fake_llm=fake)._execute_llm_turn(
        _spec(), messages, [], "parent", _emit, BudgetTracker(BudgetSpec())
    )

    sent = fake.received_calls[0]["messages"]
    assert sent[0]["content"] == system  # previously cut at 6,000 chars, dropping the summary
    assert sent[1]["content"].endswith("END OF USER MESSAGE")
    assert len(sent[2]["content"]) <= 3_100
    assert sent[2]["content"].endswith("full result saved at .results/call-1.txt")


@pytest.mark.asyncio
async def test_runner_loads_the_whole_stored_chat_not_the_last_eight_messages(
    db_session, monkeypatch, tmp_path
):
    monkeypatch.setattr(task_memory, "project_dir", lambda _project_id: tmp_path)
    monkeypatch.setattr(
        "app.db.SessionLocal", sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False)
    )
    project = models.Project(name="Runner context")
    db_session.add(project)
    db_session.flush()
    agent = models.Agent(project_id=project.id, name="A", provider="fake", model="fake/demo")
    db_session.add(agent)
    db_session.flush()
    conversation = models.Conversation(project_id=project.id, agent_id=agent.id)
    db_session.add(conversation)
    db_session.commit()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    task_id = None
    for index in range(12):
        db_session.add(models.ConversationMessage(
            conversation_id=conversation.id, role="user", content=f"question {index}",
            created_at=start + timedelta(minutes=2 * index),
        ))
        db_session.commit()
        task_id, _ = task_memory.prepare_task_state(db_session, conversation, f"question {index}")
        db_session.add(models.ConversationMessage(
            conversation_id=conversation.id, role="assistant", content=f"answer {index}",
            created_at=start + timedelta(minutes=2 * index + 1),
        ))
        db_session.commit()
    request = SimpleNamespace(conversation_id=conversation.id, task_state_id=task_id, task="what was answer 0?")

    history, summary = await RunnerCore(fake_llm=FakeLLM([]))._prepare_conversation_context(
        _spec(), request, [], "", _emit, "parent", BudgetTracker(BudgetSpec())
    )

    assert summary == ""
    assert len(history) == 24
    assert history[1] == {"role": "assistant", "content": "answer 0"}


@pytest.mark.asyncio
async def test_client_supplied_history_is_trimmed_to_the_model_not_to_eight_messages(monkeypatch):
    monkeypatch.setattr("app.core.runner.get_context_window", lambda _model: 32_000)
    request = SimpleNamespace(conversation_id=None, task_state_id=None, task="now")
    supplied = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i} " + "x" * 1_500}
        for i in range(60)
    ]

    history, _ = await RunnerCore(fake_llm=FakeLLM([]))._prepare_conversation_context(
        _spec(), request, supplied, "", _emit, "parent", BudgetTracker(BudgetSpec())
    )

    assert 8 < len(history) < 60
    assert history[-1]["content"].startswith("m59")
    assert sum(len(m["content"]) for m in history) <= 32_000
