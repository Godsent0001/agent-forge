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
from app.runtime import memory
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
        self.learned_experience = agent_row.learned_experience or ""
        self.llm = llm
        self.tools = tools  # name -> Tool (normal tools AND AgentTools, same interface)
        self._db = db
        self.parallel_execution = parallel_execution

    async def _read_memory(self) -> str:
        if not self.memory_enabled:
            return "(memory disabled)"
        # Recent entries verbatim + rolling summary of everything older —
        # see app/runtime/memory.py. Bounded cost regardless of agent age,
        # unlike a raw dump of every entry ever written.
        return await memory.read_memory(self._db, self.id, self.llm)

    async def _write_memory(self, note: str) -> None:
        if not self.memory_enabled:
            return
        await memory.write_memory(self._db, self.id, note)

    async def run(self, parent_prompt: str, *, context: ExecutionContext) -> str:
        await context.emit("AgentStarted", agent_name=self.name, data={"task": parent_prompt})

        tools_summary_lines = []
        for t in self.tools.values():
            tools_summary_lines.append(f"- Tool/Sub-agent '{t.name}': {t.description}")
        tools_summary = "\n".join(tools_summary_lines) if tools_summary_lines else "No tools or sub-agents attached."

        memory_text = await self._read_memory()
        learned_exp_text = self.learned_experience or "(No learned experience accumulated yet)"

        if "[RECENT CONVERSATION HISTORY]" in parent_prompt:
            parts = parent_prompt.split("[CURRENT USER INSTRUCTION - CRITICAL HIGHEST PRIORITY]")
            history_part = parts[0].strip()
            user_part = parts[1].strip() if len(parts) > 1 else parent_prompt

            layers = [
                f"[SYSTEM PROMPT] You are agent '{self.name}'. {self.system_prompt or 'You are a helpful AI agent.'}",
                f"[TOOL-USE SCHEMA] {self.tool_use_schema or 'No additional schema rules.'}",
                f"[AVAILABLE TOOLS AND SUB-AGENTS]\n{tools_summary}\n\nInstructions: You have access to the above tools and sub-agents. Whenever a task requires using a tool or delegating to a sub-agent, choose the appropriate tool/sub-agent and provide the required input parameter. Once the tool or sub-agent returns its output, review it and return your final response to answer the user's request.",
                f"[MEMORY CONTEXT - LOWER PRIORITY BACKGROUND HISTORICAL CONTEXT]\n{memory_text}",
                f"[LEARNED EXPERIENCE & REFLECTION - NEXT HIGHEST PRIORITY AFTER USER INSTRUCTION]\n{learned_exp_text}\n\nCRITICAL DIRECTIVE FOR LEARNED EXPERIENCE: The above document contains your cumulative learned experience, reflections, and strategy insights from past runs. Apply these learnings to guide your decision-making and avoid past mistakes.",
                history_part,
                f"[CURRENT USER INSTRUCTION - CRITICAL HIGHEST PRIORITY]\n{user_part}\n\nCRITICAL DIRECTIVE: The above CURRENT USER INSTRUCTION is your top priority. Do NOT get stuck on old tasks from memory if the user is asking for something new or updated. Respond directly to this new instruction.",
            ]
        else:
            layers = [
                f"[SYSTEM PROMPT] You are agent '{self.name}'. {self.system_prompt or 'You are a helpful AI agent.'}",
                f"[TOOL-USE SCHEMA] {self.tool_use_schema or 'No additional schema rules.'}",
                f"[AVAILABLE TOOLS AND SUB-AGENTS]\n{tools_summary}\n\nInstructions: You have access to the above tools and sub-agents. Whenever a task requires using a tool or delegating to a sub-agent, choose the appropriate tool/sub-agent and provide the required input parameter. Once the tool or sub-agent returns its output, review it and return your final response to answer the user's request.",
                f"[MEMORY CONTEXT - LOWER PRIORITY BACKGROUND HISTORICAL CONTEXT]\n{memory_text}",
                f"[LEARNED EXPERIENCE & REFLECTION - NEXT HIGHEST PRIORITY AFTER USER INSTRUCTION]\n{learned_exp_text}\n\nCRITICAL DIRECTIVE FOR LEARNED EXPERIENCE: The above document contains your cumulative learned experience, reflections, and strategy insights from past runs. Apply these learnings to guide your decision-making and avoid past mistakes.",
                f"[CURRENT USER INSTRUCTION - CRITICAL HIGHEST PRIORITY]\n{parent_prompt}\n\nCRITICAL DIRECTIVE: The above CURRENT USER INSTRUCTION is your top priority. Do NOT get stuck on old tasks from memory if the user is asking for something new or updated. Respond directly to this new instruction.",
            ]
        messages = list(layers)
        tool_specs = [ToolSpec(name=t.name, description=t.description) for t in self.tools.values()]

        final_answer: str | None = None
        max_iterations = 20  # safety valve independent of recursion depth — caps a single agent's own loop
        iterations = 0
        execution_steps: list[str] = []

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

            raw_input = (decision.tool_input or "").strip()
            if not raw_input or raw_input.lower() in ["none", "previous_step", "n/a", "{}"]:
                raw_input = parent_prompt

            tool_inputs = [inp.strip() for inp in raw_input.split("\n---\n") if inp.strip()]
            if not tool_inputs:
                tool_inputs = [raw_input]

            if self.parallel_execution and len(tool_inputs) > 1:
                async def _exec_single(inp: str):
                    try:
                        return await tool.execute(inp, context=context)
                    except ToolExecutionError as e:
                        return f"ERROR: {e}"

                results = await asyncio.gather(*[_exec_single(inp) for inp in tool_inputs])
                combined_result = "\n".join([f"Result {i+1}: {res}" for i, res in enumerate(results)])
                execution_steps.append(f"Used tool '{tool.name}' (parallel) with inputs {tool_inputs} -> Results: {combined_result}")
                messages.append(
                    f"[TOOL RESULT FOR CURRENT TASK: {tool.name}] (Parallel Execution)\n{combined_result}\n\n"
                    f"CRITICAL DIRECTIVE: Use this tool result exclusively to complete the CURRENT USER TASK ({parent_prompt}). Do NOT revert to old topics in memory."
                )
            else:
                try:
                    tool_result = await tool.execute(tool_inputs[0], context=context)
                except ToolExecutionError as e:
                    tool_result = f"ERROR: {e}"
                execution_steps.append(f"Used tool '{tool.name}' with input '{tool_inputs[0]}' -> Result: {tool_result}")
                messages.append(
                    f"[TOOL RESULT FOR CURRENT TASK: {tool.name}]\n{tool_result}\n\n"
                    f"CRITICAL DIRECTIVE: Use this tool result exclusively to complete the CURRENT USER TASK ({parent_prompt}). Do NOT revert to old topics in memory."
                )

        await self._write_memory(f"Task '{parent_prompt}' -> {final_answer}")

        # Retransform learned experience based on this execution's history & outcome
        await self._update_learned_experience(parent_prompt, execution_steps, final_answer)

        await context.emit("AgentCompleted", agent_name=self.name, data={"result": final_answer})
        return final_answer

    async def _update_learned_experience(self, parent_prompt: str, execution_steps: list[str], final_answer: str) -> None:
        try:
            agent_row = self._db.get(models.Agent, self.id)
            existing_experience = agent_row.learned_experience if agent_row else self.learned_experience

            new_experience = await self.llm.synthesize_learned_experience(
                agent_name=self.name,
                existing_learned_experience=existing_experience or "",
                task_input=parent_prompt,
                execution_steps=execution_steps,
                final_answer=final_answer,
            )

            self.learned_experience = new_experience
            if agent_row:
                agent_row.learned_experience = new_experience
                self._db.commit()
        except Exception as e:
            # Non-blocking error logging to ensure agent run still succeeds even if synthesis fails
            import logging
            logging.getLogger("agentforge.runtime").exception(f"Failed to update learned experience for agent {self.name}: {e}")
