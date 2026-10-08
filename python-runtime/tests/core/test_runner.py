import asyncio
import tempfile
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from app.contracts.checks import check_events
from app.contracts.events import RunEvent
from app.contracts.graph import AgentGraph, AgentSpec, ChildLink, ToolBinding
from app.contracts.run import BudgetSpec, RunOptions, RunRequest
from app.contracts.tools import ArtifactRef, Tool, ToolResult
from app.core.llm.fake import FakeLLM
from app.core.llm.types import LLMError, LLMTurn, ToolCall
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


class FailingToolFactory:
    def build(self, binding: ToolBinding) -> Tool:
        class FailingTool(Tool):
            kind = binding.kind
            default_description = "Failing test tool"

            async def run(self, args: dict, ctx: Any) -> ToolResult:
                raise RuntimeError("simulated tool failure")

        return FailingTool()


class SlowToolFactory:
    def build(self, binding: ToolBinding) -> Tool:
        class SlowTool(Tool):
            kind = binding.kind
            default_description = "Slow test tool"

            async def run(self, args: dict, ctx: Any) -> ToolResult:
                await asyncio.sleep(30)
                return ToolResult(ok=True, content="unexpected completion")

        return SlowTool()


@pytest.mark.asyncio
async def test_runner_tool_failure_is_returned_to_model_and_run_recovers():
    fake_llm = FakeLLM([
        LLMTurn(
            text="Calling the tool.",
            tool_calls=[ToolCall(id="fail-1", name="failing_tool", arguments={})],
        ),
        LLMTurn(text="I recovered after the tool failed."),
    ])
    runner = RunnerCore(fake_llm=fake_llm)

    graph = AgentGraph(
        root_id="root_1",
        agents={
            "root_1": AgentSpec(
                id="root_1",
                name="Recovery Agent",
                provider="fake",
                model="fake-model",
                tools=[ToolBinding(id="tb1", kind="failing_tool", name="failing_tool")],
            )
        },
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        req = RunRequest(
            execution_id="exec_fail",
            project_id="proj_1",
            root_agent_id="root_1",
            task="Use the failing tool and recover",
        )

        result = await runner.run(
            req=req,
            graph=graph,
            emit=noop_emit,
            cancel=MockCancelToken(),
            approvals=MockApprovalGate(),
            workspace=MockWorkspace(Path(tmpdir)),
            tools=FailingToolFactory(),
            memory=None,
            lessons=None,
            intents=None,
            run_history=None,
        )

    assert result.status == "completed"
    assert "recovered" in result.final_output
    assert len(fake_llm.received_calls) == 2
    tool_messages = [m for m in fake_llm.received_calls[1]["messages"] if m["role"] == "tool"]
    assert tool_messages
    assert "tool crashed (RuntimeError: simulated tool failure)" in tool_messages[-1]["content"]


@pytest.mark.asyncio
async def test_runner_cancel_closes_tool_and_agent_spans():
    fake_llm = FakeLLM([
        LLMTurn(
            text="Starting slow work.",
            tool_calls=[ToolCall(id="slow-1", name="slow_tool", arguments={})],
        ),
    ])
    runner = RunnerCore(fake_llm=fake_llm)

    graph = AgentGraph(
        root_id="root_1",
        agents={
            "root_1": AgentSpec(
                id="root_1",
                name="Slow Agent",
                provider="fake",
                model="fake-model",
                tools=[ToolBinding(id="tb1", kind="slow_tool", name="slow_tool")],
            )
        },
    )

    events = []
    async def emit(draft):
        events.append(draft)

    with tempfile.TemporaryDirectory() as tmpdir:
        req = RunRequest(
            execution_id="exec_cancel",
            project_id="proj_1",
            root_agent_id="root_1",
            task="Cancel this run",
        )

        task = asyncio.create_task(
            runner.run(
                req=req,
                graph=graph,
                emit=emit,
                cancel=MockCancelToken(),
                approvals=MockApprovalGate(),
                workspace=MockWorkspace(Path(tmpdir)),
                tools=SlowToolFactory(),
                memory=None,
                lessons=None,
                intents=None,
                run_history=None,
            )
        )
        await asyncio.sleep(0.01)
        task.cancel()
        result = await task

    assert result.status == "cancelled"
    started = {event.span_id for event in events if event.type == "span_started"}
    ended = {event.span_id: event for event in events if event.type == "span_ended"}
    assert started == set(ended)
    assert any(event.status == "cancelled" for event in ended.values())


class RequiredArg(BaseModel):
    value: str


class SchemaToolFactory:
    def build(self, binding: ToolBinding) -> Tool:
        class SchemaTool(Tool):
            kind = binding.kind
            default_description = "Schema test tool"
            Input = RequiredArg

            async def run(self, args: RequiredArg, ctx: Any) -> ToolResult:
                return ToolResult(ok=True, content=f"accepted {args.value}")

        return SchemaTool()


@pytest.mark.asyncio
async def test_runner_parallel_tool_calls_preserve_result_order():
    fake_llm = FakeLLM([
        LLMTurn(
            text="Running both tools.",
            tool_calls=[
                ToolCall(id="p1", name="first_tool", arguments={}),
                ToolCall(id="p2", name="second_tool", arguments={}),
            ],
        ),
        LLMTurn(text="Both tools completed."),
    ])
    runner = RunnerCore(fake_llm=fake_llm)
    graph = AgentGraph(
        root_id="root_1",
        agents={
            "root_1": AgentSpec(
                id="root_1",
                name="Parallel Agent",
                provider="fake",
                model="fake-model",
                tools=[
                    ToolBinding(id="tb1", kind="first_tool", name="first_tool"),
                    ToolBinding(id="tb2", kind="second_tool", name="second_tool"),
                ],
            )
        },
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        result = await runner.run(
            req=RunRequest(
                execution_id="exec_parallel",
                project_id="proj_1",
                root_agent_id="root_1",
                task="Run both",
                options=RunOptions(parallel_tools=True),
            ),
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

    assert result.status == "completed"
    assert result.totals.tool_calls == 2
    tool_messages = [m for m in fake_llm.received_calls[1]["messages"] if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_messages] == ["p1", "p2"]


@pytest.mark.asyncio
async def test_runner_unknown_tool_is_recoverable():
    fake_llm = FakeLLM([
        LLMTurn(
            text="Trying an unavailable tool.",
            tool_calls=[ToolCall(id="unknown-1", name="missing_tool", arguments={})],
        ),
        LLMTurn(text="I can continue without that tool."),
    ])
    runner = RunnerCore(fake_llm=fake_llm)
    graph = AgentGraph(
        root_id="root_1",
        agents={"root_1": AgentSpec(id="root_1", name="Agent", provider="fake", model="fake-model")},
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        result = await runner.run(
            req=RunRequest(
                execution_id="exec_unknown",
                project_id="proj_1",
                root_agent_id="root_1",
                task="Use the missing tool",
            ),
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

    assert result.status == "completed"
    assert "continue" in result.final_output
    tool_messages = [m for m in fake_llm.received_calls[1]["messages"] if m["role"] == "tool"]
    assert "ERROR: unknown tool 'missing_tool'" in tool_messages[-1]["content"]


@pytest.mark.asyncio
async def test_runner_invalid_tool_args_are_recoverable():
    fake_llm = FakeLLM([
        LLMTurn(
            text="Calling with bad args.",
            tool_calls=[ToolCall(id="bad-1", name="schema_tool", arguments={})],
        ),
        LLMTurn(text="I corrected the input."),
    ])
    runner = RunnerCore(fake_llm=fake_llm)
    graph = AgentGraph(
        root_id="root_1",
        agents={
            "root_1": AgentSpec(
                id="root_1",
                name="Agent",
                provider="fake",
                model="fake-model",
                tools=[ToolBinding(id="tb1", kind="schema_tool", name="schema_tool")],
            )
        },
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        result = await runner.run(
            req=RunRequest(
                execution_id="exec_bad_args",
                project_id="proj_1",
                root_agent_id="root_1",
                task="Use the schema tool",
            ),
            graph=graph,
            emit=noop_emit,
            cancel=MockCancelToken(),
            approvals=MockApprovalGate(),
            workspace=MockWorkspace(Path(tmpdir)),
            tools=SchemaToolFactory(),
            memory=None,
            lessons=None,
            intents=None,
            run_history=None,
        )

    assert result.status == "completed"
    assert "corrected" in result.final_output
    tool_messages = [m for m in fake_llm.received_calls[1]["messages"] if m["role"] == "tool"]
    assert "ERROR: invalid arguments for 'schema_tool'" in tool_messages[-1]["content"]


@pytest.mark.asyncio
async def test_runner_sub_agent_failure_is_recoverable():
    fake_llm = FakeLLM([
        LLMTurn(
            text="Delegating.",
            tool_calls=[ToolCall(id="sub-fail", name="research_child", arguments={"task": "research"})],
        ),
        LLMError("simulated child LLM failure"),
        LLMTurn(text="I recovered from the failed sub-agent."),
    ])
    runner = RunnerCore(fake_llm=fake_llm)
    graph = AgentGraph(
        root_id="root_1",
        agents={
            "root_1": AgentSpec(
                id="root_1",
                name="CEO",
                provider="fake",
                model="fake-model",
                children=[ChildLink(agent_id="research_child", description="Research")],
            ),
            "research_child": AgentSpec(
                id="research_child",
                name="Research",
                provider="fake",
                model="fake-model",
            ),
        },
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        result = await runner.run(
            req=RunRequest(
                execution_id="exec_sub_fail",
                project_id="proj_1",
                root_agent_id="root_1",
                task="Recover from research failure",
            ),
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

    assert result.status == "completed"
    assert "recovered" in result.final_output


@pytest.mark.asyncio
async def test_runner_loop_detection_forces_tool_free_final_turn():
    fake_llm = FakeLLM([
        LLMTurn(text="again", tool_calls=[ToolCall(id="loop-1", name="loop_tool", arguments={"x": 1})]),
        LLMTurn(text="again", tool_calls=[ToolCall(id="loop-2", name="loop_tool", arguments={"x": 1})]),
        LLMTurn(text="again", tool_calls=[ToolCall(id="loop-3", name="loop_tool", arguments={"x": 1})]),
        LLMTurn(text="Forced final answer."),
    ])
    runner = RunnerCore(fake_llm=fake_llm)
    graph = AgentGraph(
        root_id="root_1",
        agents={
            "root_1": AgentSpec(
                id="root_1",
                name="Loop Agent",
                provider="fake",
                model="fake-model",
                tools=[ToolBinding(id="tb1", kind="loop_tool", name="loop_tool")],
            )
        },
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        result = await runner.run(
            req=RunRequest(
                execution_id="exec_loop",
                project_id="proj_1",
                root_agent_id="root_1",
                task="Avoid looping",
            ),
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

    assert result.status == "completed"
    assert result.final_output == "Forced final answer."
    assert len(fake_llm.received_calls) == 4
    assert fake_llm.received_calls[-1]["tools"] == []


@pytest.mark.asyncio
async def test_runner_depth_limit_is_recoverable():
    fake_llm = FakeLLM([
        LLMTurn(
            text="Delegating.",
            tool_calls=[ToolCall(id="depth-1", name="child", arguments={"task": "too deep"})],
        ),
        LLMTurn(text="I can answer without the child."),
    ])
    runner = RunnerCore(fake_llm=fake_llm)
    graph = AgentGraph(
        root_id="root_1",
        agents={
            "root_1": AgentSpec(
                id="root_1",
                name="Root",
                provider="fake",
                model="fake-model",
                children=[ChildLink(agent_id="child")],
            ),
            "child": AgentSpec(
                id="child",
                name="Child",
                provider="fake",
                model="fake-model",
            ),
        },
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        result = await runner.run(
            req=RunRequest(
                execution_id="exec_depth",
                project_id="proj_1",
                root_agent_id="root_1",
                task="Respect depth",
                options=RunOptions(max_depth=0),
            ),
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

    assert result.status == "completed"
    assert "answer without" in result.final_output


@pytest.mark.asyncio
async def test_runner_cycle_stops_with_error_status():
    fake_llm = FakeLLM([
        LLMTurn(
            text="Root delegates.",
            tool_calls=[ToolCall(id="cycle-1", name="child", arguments={"task": "cycle"})],
        ),
        LLMTurn(
            text="Child delegates back.",
            tool_calls=[ToolCall(id="cycle-2", name="root_1", arguments={"task": "cycle back"})],
        ),
    ])
    runner = RunnerCore(fake_llm=fake_llm)
    graph = AgentGraph(
        root_id="root_1",
        agents={
            "root_1": AgentSpec(
                id="root_1",
                name="Root",
                provider="fake",
                model="fake-model",
                children=[ChildLink(agent_id="child")],
            ),
            "child": AgentSpec(
                id="child",
                name="Child",
                provider="fake",
                model="fake-model",
                children=[ChildLink(agent_id="root_1")],
            ),
        },
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        result = await runner.run(
            req=RunRequest(
                execution_id="exec_cycle",
                project_id="proj_1",
                root_agent_id="root_1",
                task="Detect the cycle",
            ),
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

    assert result.status == "error"
    assert "Cycle detected" in result.error


@pytest.mark.asyncio
async def test_runner_sub_agent_trace_passes_contract_checker():
    fake_llm = FakeLLM([
        LLMTurn(
            text="Delegating.",
            tool_calls=[ToolCall(id="trace-1", name="research_child", arguments={"task": "research"})],
        ),
        LLMTurn(text="Research complete."),
        LLMTurn(text="Final answer."),
    ])
    runner = RunnerCore(fake_llm=fake_llm)

    graph = AgentGraph(
        root_id="root_1",
        agents={
            "root_1": AgentSpec(
                id="root_1",
                name="CEO",
                provider="fake",
                model="fake-model",
                children=[ChildLink(agent_id="research_child")],
            ),
            "research_child": AgentSpec(
                id="research_child",
                name="Research",
                provider="fake",
                model="fake-model",
            ),
        },
    )

    drafts = []

    async def emit(draft):
        drafts.append(draft)

    with tempfile.TemporaryDirectory() as tmpdir:
        result = await runner.run(
            req=RunRequest(
                execution_id="exec_trace",
                project_id="proj_1",
                root_agent_id="root_1",
                task="Trace delegation",
            ),
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

    events = [
        RunEvent(
            execution_id="exec_trace",
            seq=seq,
            ts="2026-10-07T12:00:00Z",
            type=draft.type,
            span_id=draft.span_id,
            parent_span_id=draft.parent_span_id,
            kind=draft.kind,
            name=draft.name,
            status=draft.status,
            data=draft.data,
        )
        for seq, draft in enumerate(drafts, 1)
    ]

    assert result.status == "completed"
    assert check_events(events, platform_events=False) == []
