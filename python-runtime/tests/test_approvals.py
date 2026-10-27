from __future__ import annotations

import asyncio

import pytest

from app.infra.approvals import PENDING, ApprovalGateImpl, resolve_approval


@pytest.mark.asyncio
async def test_shell_runs_without_per_call_approval_by_default():
    events = []

    async def emit(event):
        events.append(event)

    gate = ApprovalGateImpl(
        execution_id="run-shell",
        settings={},
        emit=emit,
        tool_kinds={"shell": "shell"},
    )
    assert await gate.check(
        tool="shell", permissions={"subprocess"}, args_preview="mkdir demo", span_id="shell-span"
    ) is True
    assert events == []


@pytest.mark.asyncio
async def test_explicit_ask_policy_still_requests_approval():
    events = []

    async def emit(event):
        events.append(event)

    gate = ApprovalGateImpl(
        execution_id="run-1",
        settings={"tool_policy": {"project_manager": "ask"}},
        emit=emit,
        tool_kinds={"project_manager": "project_manager"},
        timeout_seconds=1,
    )
    task = asyncio.create_task(gate.check(
        tool="project_manager", permissions={"fs_write"}, args_preview='{"action":"update"}', span_id="span-1"
    ))
    for _ in range(20):
        if any(item.execution_id == "run-1" for item in PENDING.values()):
            break
        await asyncio.sleep(0)
    approval_id = next(key for key, item in PENDING.items() if item.execution_id == "run-1")
    assert events[0].type == "approval_requested"
    assert resolve_approval(execution_id="run-1", approval_id=approval_id, decision="allow_once")
    assert await task is True
    assert events[-1].type == "approval_resolved"
    assert events[-1].data["allowed"] is True


@pytest.mark.asyncio
async def test_persistent_shared_state_mutator_defaults_to_allow():
    events = []

    async def emit(event):
        events.append(event)

    gate = ApprovalGateImpl(
        execution_id="run-shared-writer",
        settings={},
        emit=emit,
        tool_kinds={"asset_cache_store": "asset_cache_store"},
    )
    assert await gate.check(
        tool="asset_cache_store",
        permissions={"fs_write"},
        args_preview='{"action":"store"}',
        span_id="writer-span",
    ) is True
    assert events == []

@pytest.mark.asyncio
async def test_project_deny_policy_blocks_without_prompt():
    events = []

    async def emit(event):
        events.append(event)

    gate = ApprovalGateImpl(
        execution_id="run-2",
        settings={"tool_policy": {"python": "deny"}},
        emit=emit,
    )
    assert await gate.check(
        tool="python", permissions={"subprocess"}, args_preview="{}", span_id="s"
    ) is False
    assert events == []


@pytest.mark.asyncio
async def test_allow_run_is_limited_to_exact_tool_name():
    events = []

    async def emit(event):
        events.append(event)

    gate = ApprovalGateImpl(
        execution_id="run-3",
        settings={"tool_policy": {"python": "ask"}},
        emit=emit,
        timeout_seconds=1,
    )
    first = asyncio.create_task(gate.check(
        tool="python", permissions={"subprocess"}, args_preview="{}", span_id="s1"
    ))
    for _ in range(20):
        if any(value.execution_id == "run-3" for value in PENDING.values()):
            break
        await asyncio.sleep(0)
    approval_id = next(key for key, value in PENDING.items() if value.execution_id == "run-3")
    assert resolve_approval(execution_id="run-3", approval_id=approval_id, decision="allow_run")
    assert await first is True
    assert await gate.check(
        tool="python", permissions={"subprocess"}, args_preview="{}", span_id="s2"
    ) is True
    other = asyncio.create_task(gate.check(
        tool="python-other", permissions={"subprocess"}, args_preview="{}", span_id="s3"
    ))
    for _ in range(20):
        if any(value.execution_id == "run-3" and value.tool == "python-other" for value in PENDING.values()):
            break
        await asyncio.sleep(0)
    other_id = next(
        key for key, value in PENDING.items()
        if value.execution_id == "run-3" and value.tool == "python-other"
    )
    assert resolve_approval(execution_id="run-3", approval_id=other_id, decision="deny")
    assert await other is False
    assert len([event for event in events if event.type == "approval_requested"]) == 2


@pytest.mark.asyncio
async def test_approval_timeout_denies_and_cleans_pending():
    events = []

    async def emit(event):
        events.append(event)

    gate = ApprovalGateImpl(
        execution_id="run-4",
        settings={"tool_policy": {"python": "ask"}},
        emit=emit,
        timeout_seconds=0.01,
    )
    assert await gate.check(
        tool="python", permissions={"subprocess"}, args_preview="{}", span_id="s"
    ) is False
    assert not any(value.execution_id == "run-4" for value in PENDING.values())
    assert events[-1].type == "approval_resolved"
    assert events[-1].data["timed_out"] is True


@pytest.mark.asyncio
async def test_cancelling_pending_approval_cleans_up():
    events = []

    async def emit(event):
        events.append(event)

    gate = ApprovalGateImpl(
        execution_id="run-5",
        settings={"tool_policy": {"python": "ask"}},
        emit=emit,
        timeout_seconds=1,
    )
    task = asyncio.create_task(gate.check(
        tool="python", permissions={"subprocess"}, args_preview="{}", span_id="s"
    ))
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


@pytest.mark.asyncio
async def test_unknown_tool_type_defaults_to_ask():
    events = []

    async def emit(event):
        events.append(event)

    gate = ApprovalGateImpl(
        execution_id="run-unknown",
        settings={},
        emit=emit,
        tool_kinds={"mystery_tool": "mystery_tool"},
        timeout_seconds=1,
    )
    task = asyncio.create_task(gate.check(
        tool="mystery_tool", permissions=set(), args_preview="{}", span_id="unknown-span"
    ))
    for _ in range(20):
        if any(item.execution_id == "run-unknown" for item in PENDING.values()):
            break
        await asyncio.sleep(0)
    approval_id = next(key for key, item in PENDING.items() if item.execution_id == "run-unknown")
    assert events[0].type == "approval_requested"
    assert resolve_approval(execution_id="run-unknown", approval_id=approval_id, decision="deny")
    assert await task is False


@pytest.mark.asyncio
async def test_explicit_ask_policy_is_honored_for_routine_tools():
    events = []

    async def emit(event):
        events.append(event)

    gate = ApprovalGateImpl(
        execution_id="run-explicit-ask",
        settings={"tool_policy": {"shell": "ask"}},
        emit=emit,
        tool_kinds={"shell": "shell"},
        timeout_seconds=1,
    )
    task = asyncio.create_task(gate.check(
        tool="shell", permissions={"subprocess"}, args_preview="mkdir demo", span_id="shell-span"
    ))
    for _ in range(20):
        if any(item.execution_id == "run-explicit-ask" for item in PENDING.values()):
            break
        await asyncio.sleep(0)
    approval_id = next(key for key, item in PENDING.items() if item.execution_id == "run-explicit-ask")
    assert events[0].type == "approval_requested"
    assert resolve_approval(execution_id="run-explicit-ask", approval_id=approval_id, decision="allow_once")
    assert await task is True
