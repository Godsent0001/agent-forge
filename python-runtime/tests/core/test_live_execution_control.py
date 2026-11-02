from __future__ import annotations

import asyncio
from uuid import uuid4
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.contracts.events import EventDraft
from app.contracts.graph import AgentGraph, AgentSpec
from app.core.llm.types import ToolCall
from app.core.runner import ReplyUserTool, RunnerCore
from app.contracts.tools import ToolResult
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
async def test_live_replacement_instruction_interrupts_an_obsolete_tool():
    token = CancelTokenImpl()
    started = asyncio.Event()

    async def long_running_tool():
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(long_running_tool())
    token.register_tool("tool-call-replan", task)
    await started.wait()

    instruction = "Use PostgreSQL instead of MongoDB."
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


@pytest.mark.asyncio
async def test_runner_can_stop_one_active_tool_without_cancelling_the_run(tmp_path):
    runner = RunnerCore()
    token = CancelTokenImpl()
    started = asyncio.Event()
    stopped = asyncio.Event()

    class Input(BaseModel):
        value: str = "test"

    class SlowTool:
        kind = "slow"
        Input = Input
        permissions = set()

        async def run(self, args, ctx):
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                stopped.set()
                raise
            return ToolResult(content="unexpected completion")

    spec = AgentSpec(
        id="agent-stop",
        name="Stop test",
        provider="venice",
        model="test-model",
    )
    graph = AgentGraph(root_id=spec.id, agents={spec.id: spec})
    events = []

    async def emit(event):
        events.append(event)

    tool_task = asyncio.create_task(runner._execute_single_tool(
        tc=ToolCall(id="tool-call-stop", name="slow", arguments={}),
        spec=spec,
        graph=graph,
        tool_instances={"slow": SlowTool()},
        req=SimpleNamespace(execution_id="run-stop", project_id="project-stop"),
        parent_span_id=None,
        depth=0,
        emit=emit,
        cancel=token,
        approvals=SimpleNamespace(check=lambda **kwargs: _allow_tool()),
        workspace=SimpleNamespace(root=tmp_path),
        tools_factory=None,
        memory=None,
        lessons=None,
        intents=None,
        run_history=None,
        budget=SimpleNamespace(record_tool_call=lambda: None),
        active_agent_ids=set(),
    ))
    await started.wait()
    assert token.stop_tool("tool-call-stop") is True
    result = await tool_task

    assert stopped.is_set()
    assert token.cancelled is False
    assert "was stopped before completion" in result


async def _allow_tool() -> bool:
    return True


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

    reply = next(tool for tool in specs if tool.name == "agentforge_reply_user")
    assert reply.parameters["properties"]["message"]["type"] == "string"
    assert isinstance(instances["agentforge_reply_user"], ReplyUserTool)
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
