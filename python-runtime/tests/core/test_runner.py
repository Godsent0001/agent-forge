from typing import Any
import pytest
from pathlib import Path
import tempfile
from app.contracts.graph import AgentGraph, AgentSpec, ChildLink, ToolBinding
from app.contracts.run import BudgetSpec, RunOptions, RunRequest
from app.contracts.tools import ArtifactRef, Tool, ToolResult
from app.contracts.checks import check_events
from app.contracts.events import EventDraft, RunEvent
from app.core.budget import BudgetTracker
from app.core.checkpoint import AgentFrame, ExecutionCheckpoint, SQLiteCheckpointStore
from app.core.runner import _fingerprint
from app.core.llm.fake import FakeLLM
from app.core.llm.types import LLMTurn, ToolCall, Usage
from app.core.runner import RunnerCore


class MockCancelToken:
    @property
    def cancelled(self) -> bool:
        return False
    def raise_if_cancelled(self) -> None:
        pass


class MockApprovalGate:
    async def check(self, *, tool: str, permissions: set, args_preview: str, span_id: str, force: bool = False, reason: str = "") -> bool:
        return True


class MockWorkspace:
    def __init__(self, root: Path):
        self.root = root
    def resolve(self, rel: str) -> Path:
        return self.root / rel
    def new_path(self, name: str) -> Path:
        return self.root / name
    def relative(self, p: Path) -> str:
        return str(p.relative_to(self.root))
    def write_result(self, tool_call_id: str, content: str) -> ArtifactRef:
        res_dir = self.root / ".results"
        res_dir.mkdir(parents=True, exist_ok=True)
        p = res_dir / f"{tool_call_id}.txt"
        p.write_text(content, encoding="utf-8")
        return ArtifactRef(path=str(p.relative_to(self.root)))


class MockToolFactory:
    def build(self, binding: ToolBinding) -> Tool:
        class SampleTool(Tool):
            kind = binding.kind
            default_description = "Sample tool"
            async def run(self, args: dict, ctx: Any) -> ToolResult:
                return ToolResult(ok=True, content=f"Result of {binding.kind}")
        return SampleTool()


async def noop_emit(draft: Any) -> None:
    pass


@pytest.mark.asyncio
async def test_runner_single_answer():
    fake_llm = FakeLLM([
        LLMTurn(text="Paris is the capital of France.")
    ])
    runner = RunnerCore(fake_llm=fake_llm)

    graph = AgentGraph(
        root_id="root_1",
        agents={
            "root_1": AgentSpec(
                id="root_1",
                name="Answer Agent",
                provider="fake",
                model="fake-model",
            )
        }
    )

    raw_events = []
    seq_count = 0
    async def emit(draft):
        nonlocal seq_count
        seq_count += 1
        raw_events.append(RunEvent(
            execution_id="exec_1",
            seq=seq_count,
            ts="2026-10-06T12:00:00Z",
            type=draft.type,
            span_id=draft.span_id,
            parent_span_id=draft.parent_span_id,
            kind=draft.kind,
            name=draft.name,
            status=draft.status,
            data=draft.data,
        ))

    with tempfile.TemporaryDirectory() as tmpdir:
        req = RunRequest(
            execution_id="exec_1",
            project_id="proj_1",
            root_agent_id="root_1",
            task="What is the capital of France?",
        )

        res = await runner.run(
            req=req,
            graph=graph,
            emit=emit,
            cancel=MockCancelToken(),
            approvals=MockApprovalGate(),
            workspace=MockWorkspace(Path(tmpdir)),
            tools=MockToolFactory(),
            memory=None,
            lessons=None,
            intents=None,
            run_history=None,
        )

        assert res.status == "completed"
        assert "Paris" in res.final_output
        assert res.totals.llm_calls == 1


@pytest.mark.asyncio
async def test_runner_tool_call_flow():
    fake_llm = FakeLLM([
        LLMTurn(
            text="Let me check search.",
            tool_calls=[ToolCall(id="tc1", name="web_search", arguments={"query": "weather"})],
        ),
        LLMTurn(text="The weather is sunny."),
    ])
    runner = RunnerCore(fake_llm=fake_llm)

    graph = AgentGraph(
        root_id="root_1",
        agents={
            "root_1": AgentSpec(
                id="root_1",
                name="Search Agent",
                provider="fake",
                model="fake-model",
                tools=[ToolBinding(id="tb1", kind="web_search", name="web_search")],
            )
        }
    )

    events = []
    async def emit(draft):
        events.append(draft)

    with tempfile.TemporaryDirectory() as tmpdir:
        req = RunRequest(
            execution_id="exec_2",
            project_id="proj_1",
            root_agent_id="root_1",
            task="Check weather",
        )

        res = await runner.run(
            req=req,
            graph=graph,
            emit=emit,
            cancel=MockCancelToken(),
            approvals=MockApprovalGate(),
            workspace=MockWorkspace(Path(tmpdir)),
            tools=MockToolFactory(),
            memory=None,
            lessons=None,
            intents=None,
            run_history=None,
        )

        assert res.status == "completed"
        assert "sunny" in res.final_output
        assert res.totals.llm_calls == 2
        assert res.totals.tool_calls == 1


@pytest.mark.asyncio
async def test_runner_budget_exceeded():
    fake_llm = FakeLLM([
        LLMTurn(text="Turn 1"),
        LLMTurn(text="Turn 2"),
    ])
    runner = RunnerCore(fake_llm=fake_llm)

    graph = AgentGraph(
        root_id="root_1",
        agents={"root_1": AgentSpec(id="root_1", name="Agent", provider="fake", model="fake-model")}
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        req = RunRequest(
            execution_id="exec_b1",
            project_id="proj_1",
            root_agent_id="root_1",
            task="Task",
            options=RunOptions(budget=BudgetSpec(max_llm_calls=0)),
        )

        res = await runner.run(
            req=req,
            graph=graph,
            emit=noop_emit,
            cancel=MockCancelToken(),
            approvals=MockApprovalGate(),
            workspace=MockWorkspace(Path(tmpdir)),
            tools=MockToolFactory(),
            memory=None,
            lessons=None,
            intents=None,
            run_history=None,
        )

        assert res.status == "budget_exceeded"


@pytest.mark.asyncio
async def test_runner_sub_agent_delegation():
    fake_llm = FakeLLM([
        # Root agent delegates to research child agent
        LLMTurn(
            text="Delegating research.",
            tool_calls=[ToolCall(id="tc_sub", name="research_child", arguments={"task": "Find market size"})],
        ),
        # Child agent response
        LLMTurn(text="Market size is estimated at $10B."),
        # Root agent final answer
        LLMTurn(text="Market size is $10B based on research."),
    ])
    runner = RunnerCore(fake_llm=fake_llm)

    graph = AgentGraph(
        root_id="root_1",
        agents={
            "root_1": AgentSpec(
                id="root_1",
                name="CEO Agent",
                provider="fake",
                model="fake-model",
                children=[ChildLink(agent_id="research_child", description="Research assistant")],
            ),
            "research_child": AgentSpec(
                id="research_child",
                name="Research Agent",
                provider="fake",
                model="fake-model",
            ),
        }
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        req = RunRequest(
            execution_id="exec_sub",
            project_id="proj_1",
            root_agent_id="root_1",
            task="Analyze market size",
        )

        res = await runner.run(
            req=req,
            graph=graph,
            emit=noop_emit,
            cancel=MockCancelToken(),
            approvals=MockApprovalGate(),
            workspace=MockWorkspace(Path(tmpdir)),
            tools=MockToolFactory(),
            memory=None,
            lessons=None,
            intents=None,
            run_history=None,
        )

        assert res.status == "completed"
        assert "$10B" in res.final_output


@pytest.mark.asyncio
async def test_runner_resumes_interrupted_tool_without_replaying_it(tmp_path):
    execution_id = "resume-safe-1"
    request = RunRequest(
        execution_id=execution_id,
        project_id="project",
        root_agent_id="root",
        task="Recover safely after interruption",
    )
    graph = AgentGraph(
        root_id="root",
        agents={"root": AgentSpec(id="root", name="Root Agent", provider="fake", model="fake-model")},
    )
    root_span_id = "11111111-1111-4111-8111-111111111111"
    tool_span_id = "22222222-2222-4222-8222-222222222222"
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": request.task},
        {"role": "assistant", "content": "searching", "tool_calls": [
            {"id": "tc-interrupted", "type": "function",
             "function": {"name": "web_search", "arguments": "{}"}}
        ]},
    ]
    budget = BudgetTracker(request.options.budget)
    store = SQLiteCheckpointStore(tmp_path / ".agentforge" / "checkpoints.sqlite3")
    checkpoint = ExecutionCheckpoint(
        execution_id=execution_id,
        graph_fingerprint=_fingerprint(graph.model_dump(mode="json")),
        status="running",
        frames=[AgentFrame(
            invocation_id="33333333-3333-4333-8333-333333333333",
            agent_id="root", span_id=root_span_id, task=request.task, depth=0,
            iteration=1, messages=messages, pending_tool_call_ids=["tc-interrupted"],
        )],
        task_state={
            "messages": messages, "iterations": 1, "tool_call_history": [],
            "pending_tool_call_ids": ["tc-interrupted"], "root_span_id": root_span_id,
        },
        budget_state=budget.snapshot(),
        metadata={
            "request_fingerprint": _fingerprint(request.model_dump(mode="json", exclude={"execution_id"})),
            "root_span_id": root_span_id,
            "active_spans": [
                {"span_id": root_span_id, "parent_span_id": None, "kind": "agent", "name": "Root Agent"},
                {"span_id": tool_span_id, "parent_span_id": root_span_id, "kind": "tool_call", "name": "web_search"},
            ],
        },
    )
    await store.save(checkpoint)

    events = [
        EventDraft(type="span_started", span_id=root_span_id, parent_span_id=None,
                   kind="agent", name="Root Agent", data={}),
        EventDraft(type="span_started", span_id=tool_span_id, parent_span_id=root_span_id,
                   kind="tool_call", name="web_search", data={}),
    ]
    async def emit(draft):
        events.append(draft)

    fake_llm = FakeLLM([LLMTurn(text="Recovered without replaying the interrupted tool.")])
    result = await RunnerCore(fake_llm=fake_llm).run(
        req=request, graph=graph, emit=emit, cancel=MockCancelToken(),
        approvals=MockApprovalGate(), workspace=MockWorkspace(tmp_path),
        tools=MockToolFactory(), memory=None, lessons=None, intents=None, run_history=None,
    )

    assert result.status == "completed"
    assert "Recovered without replaying" in result.final_output
    assert len(fake_llm.received_calls) == 1
    restored_messages = fake_llm.received_calls[0]["messages"]
    assert any(
        m.get("role") == "tool" and m.get("tool_call_id") == "tc-interrupted"
        and "outcome is unknown" in m.get("content", "")
        for m in restored_messages
    )
    assert sum(e.type == "span_started" and e.span_id == root_span_id for e in events) == 1
    assert sum(e.type == "span_ended" and e.span_id == root_span_id for e in events) == 1
    assert sum(e.type == "span_ended" and e.span_id == tool_span_id for e in events) == 1
    assert await store.load(execution_id) is None


@pytest.mark.asyncio
async def test_runner_schedules_multiple_tool_calls_in_one_turn(tmp_path):
    fake_llm = FakeLLM([
        LLMTurn(
            text="I will search two independent items.",
            tool_calls=[
                ToolCall(id="scheduled-1", name="web_search", arguments={"query": "first"}),
                ToolCall(id="scheduled-2", name="web_search", arguments={"query": "second"}),
            ],
        ),
        LLMTurn(text="Both searches completed."),
    ])
    graph = AgentGraph(
        root_id="root",
        agents={"root": AgentSpec(
            id="root", name="Scheduler Agent", provider="fake", model="fake-model",
            tools=[ToolBinding(id="search", kind="web_search", name="web_search")],
        )},
    )
    request = RunRequest(
        execution_id="scheduler-batch-1", project_id="project", root_agent_id="root",
        task="Search two independent items",
        options=RunOptions(parallel_tools=True),
    )
    result = await RunnerCore(fake_llm=fake_llm).run(
        req=request, graph=graph, emit=noop_emit, cancel=MockCancelToken(),
        approvals=MockApprovalGate(), workspace=MockWorkspace(tmp_path),
        tools=MockToolFactory(), memory=None, lessons=None, intents=None, run_history=None,
    )
    assert result.status == "completed"
    assert result.totals.tool_calls == 2
    assert "Both searches completed" in result.final_output
