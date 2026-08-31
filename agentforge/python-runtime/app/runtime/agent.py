"""
Runtime Agent: the live, executable counterpart to the DB `Agent` row.
Built fresh per-execution by ExecutionEngine (app/runtime/engine.py) from
the DB config — this class itself never touches the DB directly except
for memory read/write, keeping the loop logic testable in isolation
(see the Phase 0.5 spike, whose loop this mirrors almost line for line).
"""

from __future__ import annotations

import asyncio
from sqlalchemy.orm import Session

from app import models
from app.llm import LLMDecision, LLMInterface, ToolSpec
from app.runtime.context import ExecutionContext
from app.tools.base import Tool, ToolExecutionError


class AgentExecutionError(RuntimeError):
    pass


class RuntimeAgent:
    def __init__(
        self,
        agent_row: models.Agent,
        llm: LLMInterface,
        tools: dict[str, Tool],
        db: Session,
        parallel_execution: bool = False,
    ):
        self.id = agent_row.id
        self.name = agent_row.name
        self.system_prompt = agent_row.system_prompt
        self.tool_use_schema = agent_row.tool_use_schema
        self.memory_enabled = agent_row.memory_enabled
        self.llm = llm
        self.tools = tools  # name -> Tool (normal tools AND AgentTools, same interface)
        self._db = db
        self.parallel_execution = parallel_execution

    def _read_memory(self) -> str:
        if not self.memory_enabled:
            return "(memory disabled)"
        entries = (
            self._db.query(models.MemoryEntry)
            .filter(models.MemoryEntry.agent_id == self.id)
            .order_by(models.MemoryEntry.created_at)
            .all()
        )
        return "; ".join(e.content for e in entries) if entries else "(no memory yet)"

    def _write_memory(self, note: str) -> None:
        if not self.memory_enabled:
            return
        self._db.add(models.MemoryEntry(agent_id=self.id, content=note))
        self._db.commit()

    async def run(self, parent_prompt: str, *, context: ExecutionContext) -> str:
        await context.emit("AgentStarted", agent_name=self.name, data={"task": parent_prompt})

        layers = [
            f"[SYSTEM PROMPT] {self.system_prompt}",
            f"[TOOL-USE SCHEMA] {self.tool_use_schema}",
            f"[PARENT PROMPT] {parent_prompt}",
            f"[MEMORY] {self._read_memory()}",
        ]
        messages = list(layers)
        tool_specs = [ToolSpec(name=t.name, description=t.description) for t in self.tools.values()]

        final_answer: str | None = None
        max_iterations = 20  # safety valve independent of recursion depth — caps a single agent's own loop
        iterations = 0

        while final_answer is None:
            iterations += 1
            if iterations > max_iterations:
                raise AgentExecutionError(f"Agent {self.name} exceeded {max_iterations} reasoning iterations")

            decision: LLMDecision = await self.llm.reason(messages, tool_specs)

            if decision.action == "final_answer":
                final_answer = decision.answer or ""
                continue

            tool_name = decision.tool_name or ""
            tool = self.tools.get(tool_name)
            if tool is None:
                raise AgentExecutionError(f"Agent {self.name} requested unknown tool '{tool_name}'")

            tool_inputs = [inp.strip() for inp in (decision.tool_input or "").split("\n---\n") if inp.strip()]
            if not tool_inputs:
                tool_inputs = [decision.tool_input or ""]

            if self.parallel_execution and len(tool_inputs) > 1:
                async def _exec_single(inp: str):
                    try:
                        return await tool.execute(inp, context=context)
                    except ToolExecutionError as e:
                        return f"ERROR: {e}"

                results = await asyncio.gather(*[_exec_single(inp) for inp in tool_inputs])
                combined_result = "\n".join([f"Result {i+1}: {res}" for i, res in enumerate(results)])
                messages.append(f"[TOOL RESULT: {tool.name}] (Parallel Execution)\n{combined_result}")
            else:
                try:
                    tool_result = await tool.execute(decision.tool_input or "", context=context)
                except ToolExecutionError as e:
                    tool_result = f"ERROR: {e}"
                messages.append(f"[TOOL RESULT: {tool.name}] {tool_result}")

        self._write_memory(f"Task '{parent_prompt}' -> {final_answer}")
        await context.emit("AgentCompleted", agent_name=self.name, data={"result": final_answer})
        return final_answer
