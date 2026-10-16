"""Offline end-to-end tests for calculator calls and manager-agent delegation."""
import tempfile
from pathlib import Path
from typing import Any

import pytest

from app.contracts.graph import AgentGraph, AgentSpec, ChildLink, ToolBinding
from app.contracts.run import RunRequest
from app.contracts.tools import ArtifactRef
from app.core.llm.fake import FakeLLM
from app.core.llm.types import LLMTurn, ToolCall
from app.core.runner import RunnerCore
from app.tools.registry import DefaultToolFactory


class _CancelToken:
    @property
    def cancelled(self) -> bool:
        return False

    def raise_if_cancelled(self) -> None:
        return None


class _ApprovalGate:
    async def check(
        self,
        *,
        tool: str,
        permissions: set,
        args_preview: str,
        span_id: str,
        force: bool = False,
        reason: str = "",
    ) -> bool:
        # Calculator has no side-effect permissions; this test exercises ordinary tool flow.
        return True


class _Workspace:
    def __init__(self, root: Path):
        self.root = root

    def resolve(self, rel: str) -> Path:
        return self.root / rel

    def new_path(self, name: str) -> Path:
        return self.root / name

    def relative(self, path: Path) -> str:
        return str(path.relative_to(self.root))

    def write_result(self, tool_call_id: str, content: str) -> ArtifactRef:
        result_dir = self.root / ".results"
        result_dir.mkdir(parents=True, exist_ok=True)
        path = result_dir / f"{tool_call_id}.txt"
        path.write_text(content, encoding="utf-8")
        return ArtifactRef(path=str(path.relative_to(self.root)))


async def _run(fake_llm: FakeLLM, graph: AgentGraph, root_agent_id: str, task: str):
    runner = RunnerCore(fake_llm=fake_llm)
    events: list[Any] = []

    async def emit(event):
        events.append(event)

    with tempfile.TemporaryDirectory() as temporary_dir:
        result = await runner.run(
            req=RunRequest(
                execution_id="calculator-integration-test",
                project_id="calculator-test-project",
                root_agent_id=root_agent_id,
                task=task,
            ),
            graph=graph,
            emit=emit,
            cancel=_CancelToken(),
            approvals=_ApprovalGate(),
            workspace=_Workspace(Path(temporary_dir)),
            tools=DefaultToolFactory(),
            memory=None,
            lessons=None,
            intents=None,
            run_history=None,
        )
    return result, events


@pytest.mark.asyncio
async def test_agent_calls_calculator_and_uses_its_result():
    fake_llm = FakeLLM([
        LLMTurn(
            text="I'll use the calculator for this exact decimal addition.",
            tool_calls=[
                ToolCall(
                    id="calculator-call-1",
                    name="calculator",
                    arguments={"operation": "add", "a": 0.1, "b": 0.2},
                )
            ],
        ),
        LLMTurn(text="The calculator returned exactly 0.3."),
    ])
    graph = AgentGraph(
        root_id="math_agent",
        agents={
            "math_agent": AgentSpec(
                id="math_agent",
                name="Math Agent",
                provider="fake",
                model="fake/model",
                tools=[
                    ToolBinding(
                        id="calculator-binding",
                        kind="calculator",
                        name="calculator",
                        description="Use deterministic arithmetic for every calculation.",
                        config={},
                    )
                ],
            )
        },
    )

    result, events = await _run(
        fake_llm, graph, "math_agent", "What is 0.1 plus 0.2? Use the calculator."
    )

    assert result.status == "completed"
    assert "0.3" in result.final_output
    assert result.totals.llm_calls == 2
    assert result.totals.tool_calls == 1

    # The model was given the real calculator's numeric JSON schema.
    sent_tools = fake_llm.received_calls[0]["tools"]
    calculator_spec = next(tool for tool in sent_tools if tool["name"] == "calculator")
    assert calculator_spec["parameters"]["properties"]["a"]["anyOf"]

    # After execution, the exact tool response is fed back into the next LLM turn.
    second_turn_messages = fake_llm.received_calls[1]["messages"]
    assert any(
        message.get("role") == "tool" and message.get("content") == "0.1 + 0.2 = 0.3"
        for message in second_turn_messages
    )
    assert any(
        event.type == "span_ended"
        and event.kind == "tool_call"
        and event.name == "calculator"
        and event.status == "ok"
        for event in events
    )


@pytest.mark.asyncio
async def test_manager_delegates_to_child_agent_that_calls_calculator():
    fake_llm = FakeLLM([
        # Manager delegates a task to the calculator agent.
        LLMTurn(
            text="I'll delegate the arithmetic to my calculator agent.",
            tool_calls=[
                ToolCall(
                    id="delegate-call-1",
                    name="calculator_agent",
                    arguments={"task": "Calculate 12 multiplied by 3 using the calculator."},
                )
            ],
        ),
        # Child agent makes a genuine calculator tool call.
        LLMTurn(
            text="I'll invoke the calculator with numeric arguments.",
            tool_calls=[
                ToolCall(
                    id="calculator-call-2",
                    name="calculator",
                    arguments={"operation": "multiply", "a": 12, "b": 3},
                )
            ],
        ),
        # Child consumes the tool result.
        LLMTurn(text="The calculator returned 36."),
        # Manager consumes the delegated agent's final response.
        LLMTurn(text="The delegated calculation is complete: 36."),
    ])
    graph = AgentGraph(
        root_id="manager_agent",
        agents={
            "manager_agent": AgentSpec(
                id="manager_agent",
                name="Manager Agent",
                provider="fake",
                model="fake/model",
                children=[
                    ChildLink(
                        agent_id="calculator_agent",
                        description="Delegate arithmetic tasks to the calculator agent.",
                    )
                ],
            ),
            "calculator_agent": AgentSpec(
                id="calculator_agent",
                name="Calculator Agent",
                provider="fake",
                model="fake/model",
                tools=[
                    ToolBinding(
                        id="calculator-binding",
                        kind="calculator",
                        name="calculator",
                        config={},
                    )
                ],
            ),
        },
    )

    result, events = await _run(
        fake_llm,
        graph,
        "manager_agent",
        "Ask your calculator agent to calculate 12 times 3, then report its answer.",
    )

    assert result.status == "completed"
    assert "36" in result.final_output
    assert result.totals.llm_calls == 4
    assert result.totals.tool_calls == 2

    manager_tools = fake_llm.received_calls[0]["tools"]
    assert any(tool["name"] == "calculator_agent" for tool in manager_tools)
    child_tools = fake_llm.received_calls[1]["tools"]
    assert any(tool["name"] == "calculator" for tool in child_tools)

    child_turn_messages = fake_llm.received_calls[2]["messages"]
    assert any(
        message.get("role") == "tool" and message.get("content") == "12 × 3 = 36"
        for message in child_turn_messages
    )
    manager_final_messages = fake_llm.received_calls[3]["messages"]
    assert any(
        message.get("role") == "tool" and "36" in message.get("content", "")
        for message in manager_final_messages
    )

    child_span = next(
        event for event in events
        if event.type == "span_started"
        and event.kind == "agent"
        and event.name == "Calculator Agent"
    )
    delegation_span = next(
        event for event in events
        if event.type == "span_started"
        and event.kind == "tool_call"
        and event.name == "calculator_agent"
    )
    assert child_span.parent_span_id == delegation_span.span_id


@pytest.mark.asyncio
async def test_division_by_zero_error_is_returned_to_model_for_recovery():
    fake_llm = FakeLLM([
        LLMTurn(
            text="I'll check the division with the calculator.",
            tool_calls=[
                ToolCall(
                    id="calculator-divide-zero",
                    name="calculator",
                    arguments={"operation": "divide", "a": 1, "b": 0},
                )
            ],
        ),
        LLMTurn(text="The calculator rejected division by zero, so no numeric answer is returned."),
    ])
    graph = AgentGraph(
        root_id="math_agent",
        agents={
            "math_agent": AgentSpec(
                id="math_agent",
                name="Math Agent",
                provider="fake",
                model="fake/model",
                tools=[
                    ToolBinding(
                        id="calculator-binding",
                        kind="calculator",
                        name="calculator",
                        config={},
                    )
                ],
            )
        },
    )

    result, events = await _run(
        fake_llm, graph, "math_agent", "Calculate 1 divided by 0 using the calculator."
    )

    assert result.status == "completed"
    assert "no numeric answer" in result.final_output
    assert result.totals.tool_calls == 1
    next_turn_messages = fake_llm.received_calls[1]["messages"]
    assert any(
        message.get("role") == "tool"
        and message.get("content") == "ERROR: Division by zero is not allowed."
        for message in next_turn_messages
    )
    assert any(
        event.type == "span_started"
        and event.kind == "tool_call"
        and event.name == "calculator"
        for event in events
    )


@pytest.mark.asyncio
async def test_invalid_string_operand_is_rejected_and_error_reaches_model():
    fake_llm = FakeLLM([
        LLMTurn(
            text="I'll call the calculator with structured numeric arguments.",
            tool_calls=[
                ToolCall(
                    id="calculator-invalid-operand",
                    name="calculator",
                    arguments={"operation": "add", "a": "12", "b": 3},
                )
            ],
        ),
        LLMTurn(text="The calculator rejected the string operand; numeric arguments are required."),
    ])
    graph = AgentGraph(
        root_id="math_agent",
        agents={
            "math_agent": AgentSpec(
                id="math_agent",
                name="Math Agent",
                provider="fake",
                model="fake/model",
                tools=[
                    ToolBinding(
                        id="calculator-binding",
                        kind="calculator",
                        name="calculator",
                        config={},
                    )
                ],
            )
        },
    )

    result, events = await _run(
        fake_llm, graph, "math_agent", "Add twelve and three with numeric calculator arguments."
    )

    assert result.status == "completed"
    assert "numeric arguments are required" in result.final_output
    assert result.totals.tool_calls == 1
    next_turn_messages = fake_llm.received_calls[1]["messages"]
    tool_message = next(
        message for message in next_turn_messages if message.get("role") == "tool"
    )
    assert tool_message["content"].startswith("ERROR: invalid arguments for 'calculator':")
    assert any(
        event.type == "span_started"
        and event.kind == "tool_call"
        and event.name == "calculator"
        for event in events
    )
