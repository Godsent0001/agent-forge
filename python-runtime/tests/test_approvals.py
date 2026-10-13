from __future__ import annotations

import asyncio

import pytest

from app.infra.approvals import PENDING, ApprovalGateImpl, resolve_approval


@pytest.mark.asyncio
async def test_python_waits_for_user_and_emits_resolution():
    events = []
    async def emit(event):
        events.append(event)
    gate = ApprovalGateImpl(execution_id="run-1", settings={}, emit=emit, timeout_seconds=1)
    task = asyncio.create_task(gate.check(tool="python", permissions={"subprocess"}, args_preview="{\"code\": \"print(1)\"}", span_id="span-1"))
    for _ in range(20):
        if PENDING:
            break
        await asyncio.sleep(0)
    approval_id = next(iter(PENDING))
    assert events[0].type == "approval_requested"
    assert resolve_approval(execution_id="run-1", approval_id=approval_id, decision="allow_once")
    assert await task is True
    assert events[-1].type == "approval_resolved"
    assert events[-1].data["allowed"] is True


@pytest.mark.asyncio
async def test_project_deny_policy_blocks_without_prompt():
    events = []
    async def emit(event):
        events.append(event)
    gate = ApprovalGateImpl(execution_id="run-2", settings={"tool_policy": {"python": "deny"}}, emit=emit)
    assert await gate.check(tool="python", permissions={"subprocess"}, args_preview="{}", span_id="s") is False
    assert events == []


@pytest.mark.asyncio
async def test_allow_run_remembers_tool_kind_for_one_execution():
    events = []
    async def emit(event):
        events.append(event)
    gate = ApprovalGateImpl(execution_id="run-3", settings={}, emit=emit, timeout_seconds=1)
    first = asyncio.create_task(gate.check(tool="python", permissions={"subprocess"}, args_preview="{}", span_id="s1"))
    for _ in range(20):
        if PENDING:
            break
        await asyncio.sleep(0)
    approval_id = next(key for key, value in PENDING.items() if value.execution_id == "run-3")
    assert resolve_approval(execution_id="run-3", approval_id=approval_id, decision="allow_run")
    assert await first is True
    assert await gate.check(tool="python", permissions={"subprocess"}, args_preview="{}", span_id="s2") is True
    assert len([event for event in events if event.type == "approval_requested"]) == 1


@pytest.mark.asyncio
async def test_approval_timeout_denies_and_cleans_pending():
    events = []
    async def emit(event):
        events.append(event)
    gate = ApprovalGateImpl(execution_id="run-4", settings={}, emit=emit, timeout_seconds=0.01)
    assert await gate.check(tool="python", permissions={"subprocess"}, args_preview="{}", span_id="s") is False
    assert not any(value.execution_id == "run-4" for value in PENDING.values())
    assert events[-1].type == "approval_resolved"
    assert events[-1].data["timed_out"] is True


@pytest.mark.asyncio
async def test_cancelling_pending_approval_cleans_up():
    events = []
    async def emit(event):
        events.append(event)
    gate = ApprovalGateImpl(execution_id="run-5", settings={}, emit=emit, timeout_seconds=1)
    task = asyncio.create_task(gate.check(tool="python", permissions={"subprocess"}, args_preview="{}", span_id="s"))
    for _ in range(20):
        if any(value.execution_id == "run-5" for value in PENDING.values()):
            break
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not any(value.execution_id == "run-5" for value in PENDING.values())
    assert events[-1].type == "approval_resolved"
    assert events[-1].data["cancelled"] is True
