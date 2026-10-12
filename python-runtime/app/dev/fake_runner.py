"""Scripted deterministic Runner for testing the v2 platform without an LLM."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from app.contracts.events import EventDraft
from app.contracts.graph import AgentGraph
from app.contracts.run import RunRequest, RunResult, Totals
from app.contracts.runner import ApprovalGate, CancelToken, MemoryStore, ToolFactory
from app.contracts.tools import RunWorkspace

SCENARIO_NAMES = (
    "single_answer", "ceo_research", "tool_error_recovered",
    "long_running", "approval_python", "budget_exceeded",
)
_SCENARIO_DIR = Path(__file__).with_name("scenarios")
_LEGACY_SCENARIOS: dict[str, list[dict]] = {
    "sleep_3s": [
        {"op": "agent_start"}, {"op": "sleep", "ms": 3000},
        {"op": "agent_end", "output": "FakeRunner completed after waiting."},
    ],
    "slow": [
        {"op": "agent_start"}, {"op": "sleep", "ms": 3000},
        {"op": "agent_end", "output": "FakeRunner completed after waiting."},
    ],
    "tool_call": [
        {"op": "agent_start"},
        {"op": "tool_start", "name": "fake_tool", "args": {}},
        {"op": "tool_end", "ok": True, "result": "fake result"},
        {"op": "agent_end", "output": "FakeRunner completed with a tool call."},
    ],
    "fail": [
        {"op": "agent_start"},
        {"op": "fail", "message": "Scripted FakeRunner failure"},
    ],
}


def load_scenario(name: str | None) -> list[dict]:
    """Only load named repository-owned scenarios; caller input is never treated as a path."""
    scenario = name or "ceo_research"
    if scenario in _LEGACY_SCENARIOS:
        return [dict(op) for op in _LEGACY_SCENARIOS[scenario]]
    if scenario not in SCENARIO_NAMES:
        raise ValueError(f"Unknown FakeRunner scenario {scenario!r}. Choose one of: {', '.join(SCENARIO_NAMES)}")
    try:
        operations = json.loads((_SCENARIO_DIR / f"{scenario}.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not load FakeRunner scenario {scenario!r}") from exc
    if not isinstance(operations, list) or any(not isinstance(op, dict) for op in operations):
        raise ValueError(f"FakeRunner scenario {scenario!r} must be a JSON list of operations")
    return operations


class FakeRunner:
    """Execute scripted operations while preserving span-parent and cancellation rules."""

    async def run(
        self, req: RunRequest, *, graph: AgentGraph, emit,
        cancel: CancelToken, approvals: ApprovalGate, memory: MemoryStore,
        workspace: RunWorkspace, tools: ToolFactory,
    ) -> RunResult:
        root = graph.agents.get(graph.root_id)
        if root is None:
            return RunResult(status="error", error=f"Root agent {graph.root_id!r} not found")

        operations = load_scenario(req.options.scenario)
        stack: list[dict] = []
        totals = Totals(cost_usd=0.0)
        root_output = ""
        root_started = False

        async def emit_safely(event: EventDraft) -> None:
            # Don't interrupt an event between durable persistence and publication.
            pending = asyncio.create_task(emit(event))
            try:
                await asyncio.shield(pending)
            except asyncio.CancelledError:
                try:
                    await pending
                finally:
                    raise

        async def close_open(status: str) -> None:
            while stack:
                current = stack.pop()
                data = (
                    {"output_preview": ""}
                    if current["kind"] == "agent"
                    else {"result_preview": "Span closed before completion",
                          "is_error": status != "ok", "artifacts": []}
                )
                await emit_safely(EventDraft(
                    type="span_ended", span_id=current["id"],
                    parent_span_id=current["parent_id"], kind=current["kind"],
                    name=current["name"], status=status, data=data,
                ))

        async def sleep_ms(ms: int) -> None:
            remaining = max(0, int(ms)) / 1000
            while remaining > 0:
                cancel.raise_if_cancelled()
                interval = min(remaining, 0.05)
                await asyncio.sleep(interval)
                remaining -= interval
            cancel.raise_if_cancelled()

        try:
            for op in operations:
                cancel.raise_if_cancelled()
                operation = op.get("op")

                if operation == "agent_start":
                    parent = stack[-1] if stack else None
                    if parent is None:
                        if root_started:
                            raise ValueError("A scenario must have exactly one root agent")
                        name = str(op.get("name") or root.name)
                        agent_id = str(op.get("agent_id") or root.id)
                        depth = 0
                        root_started = True
                    else:
                        if parent["kind"] != "tool_call":
                            raise ValueError("A delegated agent must be nested inside a tool_call span")
                        name = str(op.get("name") or "Sub-agent")
                        agent_id = str(op.get("agent_id") or name)
                        parent_agent = next(item for item in reversed(stack) if item["kind"] == "agent")
                        depth = parent_agent["depth"] + 1
                    span_id = str(uuid4())
                    parent_id = parent["id"] if parent else None
                                        stack.append({"id": span_id, "parent_id": parent_id,
                                  "kind": "agent", "name": name[:2000], "depth": depth})
await emit_safely(EventDraft(
                        type="span_started", span_id=span_id,
                        parent_span_id=parent_id, kind="agent", name=name[:2000],
                        data={"agent_id": agent_id[:2000], "depth": depth,
                              "input_preview": str(op.get("input", req.task))[:2000]},
                    ))

                elif operation == "agent_end":
                    if not stack or stack[-1]["kind"] != "agent":
                        raise ValueError("agent_end must close the current agent after its children")
                    current = stack.pop()
                    output = str(op.get("output", ""))
                    await emit_safely(EventDraft(
                        type="span_ended", span_id=current["id"],
                        parent_span_id=current["parent_id"], kind="agent",
                        name=current["name"], status="ok",
                        data={"output_preview": output[:2000]},
                    ))
                    if current["depth"] == 0:
                        root_output = output

                elif operation == "llm":
                    if not stack or stack[-1]["kind"] != "agent":
                        raise ValueError("llm must run inside an agent span")
                    parent = stack[-1]
                    span_id = str(uuid4())
                    name = str(op.get("name") or "llm")[:2000]
                    stack.append({
                        "id": span_id, "parent_id": parent["id"], "kind": "llm_call",
                        "name": name,
                    })
                    await emit_safely(EventDraft(
                        type="span_started", span_id=span_id,
                        parent_span_id=parent["id"], kind="llm_call", name=name,
                        data={"provider": str(op.get("provider", "fake"))[:2000],
                              "model": str(op.get("model", "fake/scenario"))[:2000],
                              "message_count": int(op.get("message_count", 1))},
                    ))
                    usage = op.get("usage") or {}
                    input_tokens = int(usage.get("input_tokens", usage.get("in", 0)))
                    output_tokens = int(usage.get("output_tokens", usage.get("out", 0)))
                    cache_tokens = int(usage.get("cache_read_tokens", 0))
                    cost = op.get("cost", 0.0)
                    totals.llm_calls += 1
                    totals.input_tokens += max(0, input_tokens)
                    totals.output_tokens += max(0, output_tokens)
                    totals.cache_read_tokens += max(0, cache_tokens)
                    if cost is None:
                        totals.cost_usd = None
                    elif totals.cost_usd is not None:
                        totals.cost_usd += max(0.0, float(cost))
                    called_tools = op.get("tools") or []
                    try:
                    await emit_safely(EventDraft(
                        type="span_ended", span_id=span_id,
                        parent_span_id=parent["id"], kind="llm_call", name=name,
                        status="ok", data={
                            "usage": {"input_tokens": input_tokens,
                                      "output_tokens": output_tokens,
                                      "cache_read_tokens": cache_tokens},
                            "cost_usd": cost,
                            "finish_reason": "tool_calls" if called_tools else "stop",
                            "tool_calls": called_tools,
                        },
                    ))

                    except asyncio.CancelledError:
                        # emit_safely finishes the end write before propagating Stop.
                        if stack and stack[-1]["id"] == span_id:
                            stack.pop()
                        raise
                    else:
                        if stack and stack[-1]["id"] == span_id:
                            stack.pop()
                    await sleep_ms(int(op.get("ms", 0)))

                elif operation == "tool_start":
                    if not stack or stack[-1]["kind"] != "agent":
                        raise ValueError("tool_start must be nested inside an agent span")
                    parent = stack[-1]
                    span_id = str(uuid4())
                    name = str(op.get("name") or op.get("tool") or "tool")[:2000]
                    args = op.get("args", {})
                    if not isinstance(args, str):
                        args = json.dumps(args, ensure_ascii=False, separators=(",", ":"))
                                        stack.append({"id": span_id, "parent_id": parent["id"],
                                  "kind": "tool_call", "name": name, "denied": False})
await emit_safely(EventDraft(
                        type="span_started", span_id=span_id,
                        parent_span_id=parent["id"], kind="tool_call", name=name,
                        data={"tool_name": name,
                              "tool_call_id": str(op.get("tool_call_id") or uuid4())[:2000],
                              "args": str(args)[:2000]},
                    ))

                elif operation == "approval":
                    tool_span = next((item for item in reversed(stack)
                                      if item["kind"] == "tool_call"), None)
                    if tool_span is None:
                        raise ValueError("approval requires an active tool_start span")
                    args = op.get("args", {})
                    if not isinstance(args, str):
                        args = json.dumps(args, ensure_ascii=False, separators=(",", ":"))
                    allowed = await approvals.check(
                        tool=str(op.get("tool") or tool_span["name"]),
                        permissions=set(op.get("permissions") or []),
                        args_preview=str(args)[:2000], span_id=tool_span["id"],
                        force=bool(op.get("force", False)),
                        reason=str(op.get("reason") or "Scenario requires approval")[:2000],
                    )
                    tool_span["denied"] = not allowed

                elif operation == "tool_end":
                    if not stack or stack[-1]["kind"] != "tool_call":
                        raise ValueError("tool_end must close the current tool_call after any child agent")
                    current = stack.pop()
                    ok = bool(op.get("ok", True)) and not current.get("denied", False)
                    result = (
                        "Tool call denied by approval policy"
                        if current.get("denied", False)
                        else str(op.get("result", "OK"))
                    )
                    totals.tool_calls += 1
                    artifacts = op.get("artifacts", [])
                    await emit_safely(EventDraft(
                        type="span_ended", span_id=current["id"],
                        parent_span_id=current["parent_id"], kind="tool_call",
                        name=current["name"], status="ok" if ok else "error",
                        data={"result_preview": result[:2000], "is_error": not ok,
                              "artifacts": artifacts if isinstance(artifacts, list) else []},
                    ))

                elif operation == "sleep":
                    await sleep_ms(int(op.get("ms", 0)))

                elif operation == "fail":
                    raise RuntimeError(str(op.get("message") or "Scripted FakeRunner failure")[:2000])

                elif operation == "budget_exceeded":
                    message = str(op.get("message") or "Scenario exceeded the run budget")[:2000]
                    await close_open("error")
                    return RunResult(status="budget_exceeded", error=message, totals=totals)

                else:
                    raise ValueError(f"Unknown FakeRunner operation: {operation!r}")

            if stack:
                raise ValueError("Scenario finished with unclosed spans")
            if not root_started:
                raise ValueError("Scenario did not start a root agent")
            return RunResult(status="completed",
                             final_output=(root_output or f"FakeRunner completed: {req.task}")[:2000],
                             totals=totals)
        except asyncio.CancelledError:
            await close_open("cancelled")
            raise
        except Exception:
            await close_open("error")
            raise
