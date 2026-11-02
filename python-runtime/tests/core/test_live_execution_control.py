from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.contracts.events import EventDraft
from app.contracts.graph import AgentGraph, AgentSpec, ChildLink
from app.contracts.tools import ToolResult
from app.core.llm.types import LLMTurn, ToolCall
from app.core.runner import ReplyUserTool, RunnerCore
from app.db import Base
from app.services import executions as execution_service
from app.services.executions import CancelTokenImpl, Emitter, Hub
from app.tools.registry import DefaultToolFactory


@pytest.mark.asyncio
async def test_agent_can_reply_while_a_tool_batch_is_still_running(monkeypatch):
    runner = RunnerCore()
    token = CancelTokenImpl()
    stop_event = asyncio.Event()
    spec = AgentSpec(
        id="agent-live-reply",
        name="Live reply agent",
        provider="venice",
        model="test-model",
    )
    events = []

    async def fake_turn(**kwargs):
        return LLMTurn(text="I am checking the current command. I will continue as soon as it finishes.")

    async def emit(event):
        events.append(event)

    monkeypatch.setattr(runner, "_execute_llm_turn", fake_turn)
    monitor = asyncio.create_task(runner._monitor_live_messages(
        spec=spec,
        messages=[
            {"role": "system", "content": "Build the requested app."},
            {"role": "assistant", "tool_calls": [{"id": "shell-call", "type": "function"}]},
        ],
        active_tool_names="shell",
        parent_span_id="agent-span",
        emit=emit,
        budget=SimpleNamespace(),
        cancel=token,
        stop_event=stop_event,
        scenario=None,
    ))

    instruction = "Can you give me a status update?"
    token.enqueue_message(instruction)
    for _ in range(50):
        if events:
            break
        await asyncio.sleep(0)

    assert len(events) == 1
    assert events[0].type == "assistant_message"
    assert events[0].data["live_response"] is True
    assert "I am checking the current command" in events[0].data["content"]
    assert token.was_message_replied(instruction)
    assert token.drain_messages() == [instruction]

    stop_event.set()
    await monitor


@pytest.mark.asyncio
async def test_agent_does_not_send_a_stale_reply_for_a_replan_instruction():
    runner = RunnerCore()
    token = CancelTokenImpl()
    stop_event = asyncio.Event()
    spec = AgentSpec(
        id="agent-replan",
        name="Replanning agent",
        provider="venice",
        model="test-model",
    )
    events = []

    async def emit(event):
        events.append(event)

    monitor = asyncio.create_task(runner._monitor_live_messages(
        spec=spec,
        messages=[{"role": "system", "content": "Build an app."}],
        active_tool_names="shell",
        parent_span_id="agent-span",
        emit=emit,
        budget=SimpleNamespace(),
        cancel=token,
        stop_event=stop_event,
        scenario=None,
    ))
    instruction = "Use PostgreSQL instead of MongoDB."
    token.enqueue_message(instruction)
    for _ in range(20):
        await asyncio.sleep(0)
    assert events == []
    assert token.drain_messages() == [instruction]
    stop_event.set()
    await monitor


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

    class SlowInput(BaseModel):
        value: str = "test"

    class SlowTool:
        kind = "slow"
        Input = SlowInput
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


@pytest.mark.asyncio
async def test_runner_can_stop_a_running_sub_agent_tool(tmp_path):
    started = asyncio.Event()

    class SlowChildRunner(RunnerCore):
        async def _run_agent(self, **kwargs):
            started.set()
            await asyncio.Event().wait()

    runner = SlowChildRunner()
    token = CancelTokenImpl()
    root = AgentSpec(
        id="root",
        name="Root",
        provider="venice",
        model="test-model",
        children=[ChildLink(agent_id="child")],
    )
    child = AgentSpec(id="child", name="Child", provider="venice", model="test-model")
    graph = AgentGraph(root_id="root", agents={"root": root, "child": child})

    async def emit(_event):
        return None

    tool_task = asyncio.create_task(runner._execute_single_tool(
        tc=ToolCall(id="child-call", name="child", arguments={"task": "do work"}),
        spec=root,
        graph=graph,
        tool_instances={},
        req=SimpleNamespace(execution_id="run-child", project_id="project-child"),
        parent_span_id=None,
        depth=0,
        emit=emit,
        cancel=token,
        approvals=None,
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
    assert token.stop_tool("child-call") is True
    result = await tool_task
    assert "sub-agent 'child' was stopped" in result
    assert token.cancelled is False


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
            assert saved.id == event.data["message_id"]
            assert len(saved.id) == 36
            assert saved.role == "assistant"
            assert saved.content == "I understand. I am updating the implementation now."
        finally:
            db.close()
    finally:
        engine.dispose()


def test_internal_tool_stop_notice_does_not_enter_live_user_notification_queue():
    token = CancelTokenImpl()
    token.record_tool_stop_notice("tool-call-internal")

    assert token._message_notifications.empty()
    drained = token.drain_messages()
    assert len(drained) == 1
    assert drained[0].startswith("[Runtime control notice]")
