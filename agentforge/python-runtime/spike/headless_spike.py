"""
Phase 0.5 — Headless Runtime Spike

Throwaway-but-real code. No UI, no database, no HTTP. Hardcodes
CEO -> Research -> Web Search and proves the four hardest architectural
claims from the spec before we build a single UI panel on top of them:

  1. An Agent and an AgentTool satisfy the *same* Tool interface, so the
     runtime never needs to know it's calling a child agent vs a plain tool.
  2. The four-layer prompt merge works: system prompt (who am I) +
     tool-use schema (how do I use tools) + parent's runtime prompt
     (what do you want right now) + memory (what do I remember).
  3. Recursion depth limit and cycle detection are enforced *at execution
     time*, not just when the graph is edited.
  4. Execution events stream out in the right order/shape for a future
     live execution-tree UI to consume.

The "LLM" here is a scripted mock — no network in this environment —
but the call sites are exactly where LiteLLM plugs in later (see
app/llm.py in Phase 4).
"""

from __future__ import annotations

import asyncio
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable


# ---------------------------------------------------------------------------
# 1. Events — the shape the future WebSocket stream (Phase 7) will emit
# ---------------------------------------------------------------------------

@dataclass
class ExecutionEvent:
    type: str
    agent_name: str | None = None
    tool_name: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


EventSink = Callable[[ExecutionEvent], None]


def console_sink(event: ExecutionEvent) -> None:
    indent = "  " * event.data.get("depth", 0)
    label = event.tool_name or event.agent_name or ""
    print(f"{indent}[{event.type}] {label} {event.data.get('note', '')}".rstrip())


# ---------------------------------------------------------------------------
# 2. The universal Tool interface — normal tools and agent-as-tool both
#    implement this. The runtime never special-cases either.
# ---------------------------------------------------------------------------

class Tool(ABC):
    name: str
    description: str

    @abstractmethod
    async def execute(self, input: str, *, context: "ExecutionContext") -> str:
        ...


class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web for current information."

    async def execute(self, input: str, *, context: "ExecutionContext") -> str:
        context.emit(ExecutionEvent("ToolCallStarted", tool_name=self.name,
                                     data={"depth": context.depth, "note": f'query="{input}"'}))
        await asyncio.sleep(0.05)  # simulate IO latency
        result = f"[mock search results for '{input}': 3 relevant articles found]"
        context.emit(ExecutionEvent("ToolCallCompleted", tool_name=self.name,
                                     data={"depth": context.depth}))
        return result


# ---------------------------------------------------------------------------
# 3. Execution context — carries depth + visited-agent set for cycle/depth
#    guards. This travels down through every recursive call.
# ---------------------------------------------------------------------------

MAX_RECURSION_DEPTH = 8


class RecursionLimitError(RuntimeError):
    pass


class CycleDetectedError(RuntimeError):
    pass


@dataclass
class ExecutionContext:
    execution_id: str
    depth: int = 0
    visited_agent_ids: tuple[str, ...] = ()
    sink: EventSink = console_sink

    def emit(self, event: ExecutionEvent) -> None:
        self.sink(event)

    def descend(self, agent_id: str) -> "ExecutionContext":
        if self.depth + 1 > MAX_RECURSION_DEPTH:
            raise RecursionLimitError(
                f"Max recursion depth ({MAX_RECURSION_DEPTH}) exceeded at agent {agent_id}"
            )
        if agent_id in self.visited_agent_ids:
            raise CycleDetectedError(
                f"Cycle detected: agent {agent_id} already active in this execution "
                f"(chain: {' -> '.join(self.visited_agent_ids)} -> {agent_id})"
            )
        return ExecutionContext(
            execution_id=self.execution_id,
            depth=self.depth + 1,
            visited_agent_ids=self.visited_agent_ids + (agent_id,),
            sink=self.sink,
        )


# ---------------------------------------------------------------------------
# 4. Mock LLM — scripted reasoning, standing in for LiteLLM (Phase 4).
#    Decides: use a tool, or give a final answer.
# ---------------------------------------------------------------------------

@dataclass
class LLMDecision:
    action: str  # "tool_call" | "final_answer"
    tool_name: str | None = None
    tool_input: str | None = None
    answer: str | None = None


class MockLLM:
    """
    Deterministic script per agent name so the spike is reproducible.
    Real version (Phase 4): agent.llm.reason(messages, available_tools) -> LLMDecision
    """

    def __init__(self, script: list[LLMDecision]):
        self._script = script
        self._step = 0

    async def reason(self, messages: list[str], available_tools: list[str]) -> LLMDecision:
        await asyncio.sleep(0.02)
        decision = self._script[min(self._step, len(self._script) - 1)]
        self._step += 1
        return decision


# ---------------------------------------------------------------------------
# 5. Agent — implements the full loop, and doubles as an AgentTool when
#    wrapped, satisfying the same Tool interface as WebSearchTool above.
# ---------------------------------------------------------------------------

@dataclass
class Memory:
    entries: list[str] = field(default_factory=list)

    def read(self) -> str:
        return "; ".join(self.entries) if self.entries else "(no memory yet)"

    def write(self, note: str) -> None:
        self.entries.append(note)


class Agent:
    def __init__(
        self,
        name: str,
        system_prompt: str,
        tool_use_schema: str,
        llm: MockLLM,
        tools: list[Tool] | None = None,
        memory_enabled: bool = False,
    ):
        self.id = str(uuid.uuid4())
        self.name = name
        self.system_prompt = system_prompt
        self.tool_use_schema = tool_use_schema
        self.llm = llm
        self.tools = {t.name: t for t in (tools or [])}
        self.memory = Memory() if memory_enabled else None

    def as_tool(self, description: str) -> "AgentTool":
        return AgentTool(agent=self, description=description)

    async def run(self, parent_prompt: str, *, context: ExecutionContext) -> str:
        context.emit(ExecutionEvent("AgentStarted", agent_name=self.name,
                                     data={"depth": context.depth, "note": f'task="{parent_prompt}"'}))

        # --- The four-layer prompt merge ---
        layers = [
            f"[SYSTEM PROMPT] {self.system_prompt}",
            f"[TOOL-USE SCHEMA] {self.tool_use_schema}",
            f"[PARENT PROMPT] {parent_prompt}",
            f"[MEMORY] {self.memory.read() if self.memory else '(memory disabled)'}",
        ]
        messages = list(layers)

        final_answer: str | None = None
        while final_answer is None:
            decision = await self.llm.reason(messages, list(self.tools.keys()))

            if decision.action == "final_answer":
                final_answer = decision.answer or ""
                continue

            tool = self.tools.get(decision.tool_name or "")
            if tool is None:
                raise RuntimeError(f"Agent {self.name} requested unknown tool '{decision.tool_name}'")

            # This is the recursive step: if `tool` is an AgentTool, this
            # call re-enters Agent.run() one level deeper. context.descend()
            # is what enforces the depth limit and cycle guard on that path.
            tool_result = await tool.execute(decision.tool_input or "", context=context)
            messages.append(f"[TOOL RESULT: {tool.name}] {tool_result}")

        if self.memory is not None:
            self.memory.write(f"Task '{parent_prompt}' -> {final_answer}")

        context.emit(ExecutionEvent("AgentCompleted", agent_name=self.name,
                                     data={"depth": context.depth, "note": f'result="{final_answer}"'}))
        return final_answer


class AgentTool(Tool):
    """Wraps an Agent so it satisfies the Tool interface for a parent agent."""

    def __init__(self, agent: Agent, description: str):
        self.agent = agent
        self.name = agent.name.lower().replace(" ", "_")
        self.description = description

    async def execute(self, input: str, *, context: ExecutionContext) -> str:
        context.emit(ExecutionEvent("ChildAgentStarted", agent_name=self.agent.name,
                                     data={"depth": context.depth}))
        child_context = context.descend(self.agent.id)
        result = await self.agent.run(input, context=child_context)
        context.emit(ExecutionEvent("ChildAgentCompleted", agent_name=self.agent.name,
                                     data={"depth": context.depth}))
        return result


# ---------------------------------------------------------------------------
# 6. Build the hardcoded hierarchy from the spec: CEO -> Research -> WebSearch
# ---------------------------------------------------------------------------

def build_hierarchy() -> Agent:
    web_search = WebSearchTool()

    research_llm = MockLLM([
        LLMDecision(action="tool_call", tool_name="web_search",
                    tool_input="top AI video companies pricing enterprise Africa"),
        LLMDecision(action="final_answer",
                    answer="Top 3 AI video companies with enterprise/Africa pricing data compiled."),
    ])
    research_agent = Agent(
        name="Research Agent",
        system_prompt="You are an expert market researcher.",
        tool_use_schema="Use web search for current information.",
        llm=research_llm,
        tools=[web_search],
        memory_enabled=True,
    )

    ceo_llm = MockLLM([
        LLMDecision(action="tool_call", tool_name="research_agent",
                    tool_input="Research the top 10 AI video companies, focus on pricing, "
                               "enterprise customers and African markets."),
        LLMDecision(action="final_answer",
                    answer="Based on research: recommend entering the African market via a "
                           "mid-tier enterprise pricing plan."),
    ])
    ceo_agent = Agent(
        name="CEO Agent",
        system_prompt="You are the CEO. Delegate research to specialists before deciding.",
        tool_use_schema="Use the research agent when market data is needed before deciding.",
        llm=ceo_llm,
        tools=[research_agent.as_tool("Performs market research tasks.")],
    )

    return ceo_agent


async def main() -> None:
    ceo = build_hierarchy()
    context = ExecutionContext(execution_id=str(uuid.uuid4()))

    context.emit(ExecutionEvent("ExecutionStarted", data={"depth": 0}))
    final = await ceo.run("Analyze the AI video market and decide whether to enter it.", context=context)
    context.emit(ExecutionEvent("ExecutionCompleted", data={"depth": 0, "note": f'final="{final}"'}))

    print("\n--- FINAL ANSWER ---")
    print(final)


async def demo_cycle_guard() -> None:
    """Proves the cycle/depth guards actually fire, not just exist on paper."""
    print("\n--- Cycle guard demo ---")
    a = Agent("A", "sys", "schema", MockLLM([LLMDecision(action="final_answer", answer="done")]))
    context = ExecutionContext(execution_id="cycle-test", visited_agent_ids=(a.id,))
    try:
        context.descend(a.id)
        print("FAIL: expected CycleDetectedError")
    except CycleDetectedError as e:
        print(f"OK: {e}")

    print("\n--- Depth guard demo ---")
    deep_context = ExecutionContext(execution_id="depth-test", depth=MAX_RECURSION_DEPTH)
    try:
        deep_context.descend("some-agent-id")
        print("FAIL: expected RecursionLimitError")
    except RecursionLimitError as e:
        print(f"OK: {e}")


if __name__ == "__main__":
    asyncio.run(main())
    asyncio.run(demo_cycle_guard())
