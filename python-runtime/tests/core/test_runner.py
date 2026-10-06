from typing import Any
import pytest
from pathlib import Path
import tempfile
from app.contracts.graph import AgentGraph, AgentSpec, ChildLink, ToolBinding
from app.contracts.run import BudgetSpec, RunOptions, RunRequest
from app.contracts.tools import ArtifactRef, Tool, ToolResult
from app.contracts.checks import check_events
from app.contracts.events import RunEvent
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
