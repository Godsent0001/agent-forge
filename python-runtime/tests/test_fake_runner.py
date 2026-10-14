import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.contracts.checks import check_events
from app.contracts.events import EventDraft, RunEvent
from app.contracts.graph import AgentGraph, AgentSpec
from app.contracts.run import RunOptions, RunRequest
from app.dev.fake_runner import SCENARIO_NAMES, FakeRunner


class _CancelToken:
    def raise_if_cancelled(self):
        return None


class RecordingApprovals:
    def __init__(self, allowed=True):
        self.allowed = allowed
        self.calls = []

    async def check(self, **kwargs):
        self.calls.append(kwargs)
        return self.allowed


def _context(scenario):
    execution_id, root_id = str(uuid4()), str(uuid4())
    request = RunRequest(
        execution_id=execution_id, project_id=str(uuid4()), root_agent_id=root_id,
        task="exercise a deterministic test scenario", options=RunOptions(scenario=scenario),
    )
    graph = AgentGraph(root_id=root_id, agents={
        root_id: AgentSpec(
            id=root_id, name="Root Agent", provider="fake", model="fake/scenario",
        )
    })
    return request, graph


def _run_events(request, drafts):
    now = datetime.now(timezone.utc)
    return [
        RunEvent(
            execution_id=request.execution_id, seq=seq,
            ts=now + timedelta(microseconds=seq), **draft.model_dump(),
        )
        for seq, draft in enumerate(drafts, 1)
    ]


async def _run_scenario(scenario, *, approvals=None):
    request, graph = _context(scenario)
    drafts: list[EventDraft] = []

    async def emit(draft):
        drafts.append(draft)

    gate = approvals or RecordingApprovals()
    result = await FakeRunner().run(
        request, graph=graph, emit=emit, cancel=_CancelToken(),
        approvals=gate, memory=None, workspace=None, tools=None,
    )
    return result, _run_events(request, drafts), gate


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", SCENARIO_NAMES)
async def test_all_scripted_scenarios_obey_the_event_contract(scenario):
    result, events, _ = await _run_scenario(scenario)
    issues = check_events(events, platform_events=False, complete=True)
    assert issues == [], "\n".join(issues)
    assert events
    assert all(e.type not in {"execution_started", "execution_ended"} for e in events)
    assert result.status == ("budget_exceeded" if scenario == "budget_exceeded" else "completed")


@pytest.mark.asyncio
async def test_approval_denial_ends_tool_as_error_without_breaking_trace():
    gate = RecordingApprovals(allowed=False)
    result, events, gate = await _run_scenario("approval_python", approvals=gate)
    assert result.status == "completed"
    assert len(gate.calls) == 1
    assert gate.calls[0]["tool"] == "python"
    tool_end = next(e for e in events if e.type == "span_ended" and e.kind == "tool_call")
    assert tool_end.status == "error"
    assert tool_end.data["is_error"] is True
    assert check_events(events, platform_events=False, complete=True) == []


@pytest.mark.asyncio
async def test_ceo_research_scenario_preserves_parent_and_depth():
    result, events, _ = await _run_scenario("ceo_research")
    assert result.status == "completed"
    root = next(e for e in events if e.type == "span_started" and e.kind == "agent" and e.name == "CEO Agent")
    research_tool = next(e for e in events if e.type == "span_started" and e.kind == "tool_call" and e.name == "research_agent")
    researcher = next(e for e in events if e.type == "span_started" and e.kind == "agent" and e.name == "Research Agent")
    assert research_tool.parent_span_id == root.span_id
    assert researcher.parent_span_id == research_tool.span_id
    assert researcher.data["depth"] == 1
    assert check_events(events, platform_events=False, complete=True) == []


@pytest.mark.asyncio
async def test_cancellation_closes_every_open_span():
    request, graph = _context("long_running")
    drafts: list[EventDraft] = []

    async def emit(draft):
        drafts.append(draft)

    task = asyncio.create_task(FakeRunner().run(
        request, graph=graph, emit=emit, cancel=_CancelToken(),
        approvals=RecordingApprovals(), memory=None, workspace=None, tools=None,
    ))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    events = _run_events(request, drafts)
    assert any(e.type == "span_ended" and e.status == "cancelled" for e in events)
    assert check_events(events, platform_events=False, complete=True) == []


@pytest.mark.asyncio
async def test_failure_closes_spans_before_propagating():
    request, graph = _context("fail")
    drafts: list[EventDraft] = []

    async def emit(draft):
        drafts.append(draft)

    with pytest.raises(RuntimeError, match="Scripted FakeRunner failure"):
        await FakeRunner().run(
            request, graph=graph, emit=emit, cancel=_CancelToken(),
            approvals=RecordingApprovals(), memory=None, workspace=None, tools=None,
        )
    assert check_events(_run_events(request, drafts), platform_events=False, complete=True) == []
