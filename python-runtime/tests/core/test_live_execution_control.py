from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.contracts.events import EventDraft
from app.contracts.graph import AgentGraph, AgentSpec
from app.core.runner import ReplyUserTool, RunnerCore
from app.db import Base
from app.services import executions as execution_service
from app.services.executions import CancelTokenImpl, Emitter, Hub
from app.tools.registry import DefaultToolFactory


@pytest.mark.asyncio
async def test_live_stop_instruction_cancels_the_active_tool_without_cancelling_the_run():
    token = CancelTokenImpl()
    started = asyncio.Event()

    async def long_running_tool():
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(long_running_tool())
    token.register_tool("tool-call-1", task)
    await started.wait()

    instruction = "Stop the current command and use the new approach instead."
    token.enqueue_message(instruction)

    with pytest.raises(asyncio.CancelledError):
        await task

    assert token.cancelled is False
    assert token.drain_messages() == [instruction]


@pytest.mark.asyncio
async def test_live_status_message_does_not_stop_an_active_tool():
    token = CancelTokenImpl()
    started = asyncio.Event()

    async def long_running_tool():
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(long_running_tool())
    token.register_tool("tool-call-2", task)
    await started.wait()

    instruction = "Can you give me a quick status update?"
    token.enqueue_message(instruction)

    assert not task.done()
    assert token.drain_messages() == [instruction]

    assert token.stop_tool("tool-call-2") is True
    with pytest.raises(asyncio.CancelledError):
        await task


def test_runner_always_exposes_an_interim_reply_control():
    spec = AgentSpec(
        id="agent-live",
        name="Live agent",
        provider="venice",
        model="test-model",
    )
    graph = AgentGraph(root_id=spec.id, agents={spec.id: spec})
    specs, instances = RunnerCore()._assemble_tools(
        spec,
        graph,
        DefaultToolFactory(),
        memory=None,
        intents=None,
        run_history=None,
    )

    reply = next(tool for tool in specs if tool.name == "reply_user")
    assert reply.parameters["properties"]["message"]["type"] == "string"
    assert isinstance(instances["reply_user"], ReplyUserTool)
    assert "continue" in reply.description.lower()


@pytest.mark.asyncio
async def test_emitter_persists_interim_replies_in_the_execution_conversation(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(execution_service, "SessionLocal", factory)
    db = factory()
    try:
        project = models.Project(name="Interim reply test")
        db.add(project)
        db.flush()
        agent = models.Agent(project_id=project.id, name="Live agent")
        db.add(agent)
        db.flush()
        conversation = models.Conversation(
            project_id=project.id,
            agent_id=agent.id,
            title="Live task",
        )
        execution_id = str(uuid4())
        execution = models.Execution(
            id=execution_id,
            project_id=project.id,
            root_agent_id=agent.id,
            input_task="Build an application",
            status="running",
        )
        db.add_all([conversation, execution])
        db.commit()
        conversation_id = conversation.id
    finally:
        db.close()

    try:
        emitter = Emitter(execution_id, Hub(), conversation_id=conversation_id)
        event = await emitter.emit(EventDraft(
            type="assistant_message",
            name="Live agent",
            data={"content": "I understand. I am updating the implementation now.", "interim": True},
        ))

        db = factory()
        try:
            saved = db.query(models.ConversationMessage).filter_by(
                execution_id=execution_id
            ).one()
            assert saved.id == f"interim-{execution_id}-{event.seq}"
            assert saved.role == "assistant"
            assert saved.content == "I understand. I am updating the implementation now."
        finally:
            db.close()
    finally:
        engine.dispose()
