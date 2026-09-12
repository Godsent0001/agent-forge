"""
Execution Engine — the piece that ties Phase 1's data model, Phase 2's
tools, Phase 4's LLM interface, and Phase 5/6's agent loop + recursion
together into one runnable execution, and persists the result.

Entry point: ExecutionEngine.run(project_id, root_agent_id, task)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import models
from app.llm import LLMInterface
from app.runtime.agent import RuntimeAgent
from app.runtime.agent_tool import AgentTool
from app.runtime.context import CycleDetectedError, ExecutionContext, ExecutionEvent, RecursionLimitError
from app.tools.base import Tool
from app.tools.registry import build_tool
from app.ws import manager


class ExecutionEngine:
    def __init__(self, db: Session):
        self._db = db
        # Cache so the same agent, if reachable via two different paths in
        # one execution, doesn't get rebuilt (and doesn't lose its memory
        # writes) mid-run.
        self._agent_cache: dict[str, RuntimeAgent] = {}

    def _build_tools_for(self, agent_row: models.Agent) -> dict[str, Tool]:
        tools: dict[str, Tool] = {}

        for link in agent_row.tool_links:
            tool_row = link.tool
            tool = build_tool(tool_row.kind, tool_row.config)
            tools[tool.name] = tool

        for link in agent_row.child_links:
            child_runtime_agent = self._build_agent(link.child_agent_id)
            desc = link.description or child_runtime_agent.system_prompt or f"Sub-agent {child_runtime_agent.name}"
            agent_tool = AgentTool(
                agent=child_runtime_agent,
                name=child_runtime_agent.name.lower().replace(" ", "_"),
                description=f"Sub-agent tool '{child_runtime_agent.name}'. Goal/Role: {desc}. Input: Task string for the sub-agent. Returns final result string.",
            )
            tools[agent_tool.name] = agent_tool

        return tools

    def _build_agent(self, agent_id: str, parallel_execution: bool = False) -> RuntimeAgent:
        if agent_id in self._agent_cache:
            return self._agent_cache[agent_id]

        agent_row = self._db.get(models.Agent, agent_id)
        if agent_row is None:
            raise ValueError(f"Agent {agent_id} not found")

        llm = LLMInterface(provider=agent_row.provider, model=agent_row.model)

        runtime_agent = RuntimeAgent.__new__(RuntimeAgent)
        self._agent_cache[agent_id] = runtime_agent

        tools = self._build_tools_for(agent_row)
        RuntimeAgent.__init__(runtime_agent, agent_row, llm, tools, self._db, parallel_execution=parallel_execution)
        return runtime_agent

    async def run(self, project_id: str, root_agent_id: str, task: str) -> models.Execution:
        execution = models.Execution(
            id=str(uuid.uuid4()),
            project_id=project_id,
            root_agent_id=root_agent_id,
            input_task=task,
            status="running",
        )
        self._db.add(execution)
        self._db.commit()

        async def sink(event: ExecutionEvent) -> None:
            row = models.ExecutionEventRow(
                execution_id=execution.id,
                type=event.type,
                agent_name=event.agent_name,
                tool_name=event.tool_name,
                depth=event.depth,
                data=event.data,
            )
            self._db.add(row)
            self._db.commit()
            await manager.broadcast(execution.id, {
                "type": event.type,
                "agent_name": event.agent_name,
                "tool_name": event.tool_name,
                "depth": event.depth,
                "data": event.data,
            })

        context = ExecutionContext(execution_id=execution.id, sink=sink)

        try:
            await context.emit("ExecutionStarted")
            project = self._db.get(models.Project, project_id)
            parallel_exec = project.parallel_execution if project else False
            root_agent = self._build_agent(root_agent_id, parallel_execution=parallel_exec)
            final_output = await root_agent.run(task, context=context)

            execution.status = "completed"
            execution.final_output = final_output
            execution.completed_at = datetime.now(timezone.utc)
            await context.emit("ExecutionCompleted", data={"final": final_output})

        except (RecursionLimitError, CycleDetectedError) as e:
            execution.status = "error"
            execution.final_output = str(e)
            execution.completed_at = datetime.now(timezone.utc)
            await context.emit("ExecutionCompleted", data={"error": str(e)})

        except Exception as e:  # noqa: BLE001 — always land the execution in a terminal state
            execution.status = "error"
            execution.final_output = f"Unexpected error: {e}"
            execution.completed_at = datetime.now(timezone.utc)
            await context.emit("ExecutionCompleted", data={"error": str(e)})

        self._db.commit()
        return execution
