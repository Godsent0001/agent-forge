"""Low-token tool for durable, structured task-memory updates."""
from __future__ import annotations

import asyncio
import json
from typing import Literal

from pydantic import BaseModel, Field

from app.contracts.tools import Permission, Tool, ToolContext, ToolError, ToolResult
from app.services.task_memory import apply_task_state_update


class PlanNodeDraft(BaseModel):
    ref: str = Field(min_length=1, max_length=64, description="Temporary reference for child nodes in this same update.")
    parent_ref: str = Field(default="root", max_length=64, description="root, an existing plan-node ID, or an earlier node ref in this update.")
    type: Literal["goal", "phase", "subgoal", "task", "milestone"]
    title: str = Field(min_length=1, max_length=120)
    objective: str = Field(default="", max_length=500)


class PlanDependencyDraft(BaseModel):
    node_ref: str = Field(min_length=1, max_length=64, description="The dependent node ID or ref.")
    depends_on_ref: str = Field(min_length=1, max_length=64, description="The prerequisite node ID or ref.")
    reason: str = Field(default="", max_length=240)


class TaskStateUpdateInput(BaseModel):
    plan_nodes_add: list[PlanNodeDraft] = Field(
        default_factory=list, max_length=8,
        description="Add agent-owned phases/subgoals/tasks to the shared hierarchy. Add parents before children and use temporary refs to nest nodes in one call.",
    )
    plan_dependencies_add: list[PlanDependencyDraft] = Field(
        default_factory=list, max_length=8,
        description="Add prerequisite relationships between existing or newly-added plan nodes. Do not create cycles.",
    )
    decisions_add: list[str] = Field(
        default_factory=list, max_length=5,
        description="New decisions explicitly stated or approved by the user. Do not store your own suggestions as accepted decisions; put agent proposals in the execution-plan nodes.",
    )
    constraints_add: list[str] = Field(
        default_factory=list, max_length=5,
        description="Requirements or constraints explicitly stated by the user. Do not promote agent assumptions into user constraints.",
    )
    completed_add: list[str] = Field(
        default_factory=list, max_length=5,
        description="Milestones verified as completed by actual execution evidence.",
    )
    remaining: list[str] | None = Field(
        default=None, max_length=12,
        description="Replace the outstanding-work list. Omit to leave it unchanged; use [] to clear it.",
    )
    blockers: list[str] | None = Field(
        default=None, max_length=12,
        description="Replace the current blocker list. Omit to leave it unchanged; use [] to clear it.",
    )
    next_action: str | None = Field(
        default=None, max_length=300,
        description="The single most useful next action. Omit to leave unchanged; use an empty string to clear.",
    )
    note: str = Field(
        default="", max_length=300,
        description="Brief reason for this memory update.",
    )


class TaskStateUpdateTool(Tool):
    kind = "task_state_update"
    default_description = (
        "Persist meaningful task memory: agent execution-plan nodes/dependencies, decisions, constraints, "
        "verified completed milestones, remaining work, blockers, and the next action. Only record user-approved decisions/constraints as binding; keep agent assumptions separate. Batch several changes into one call. "
        "Use this only at meaningful milestones or when a durable decision/constraint changes; "
        "do not call after every trivial tool result. Never mark work completed without evidence. "
        "The original objective is immutable."
    )
    Input = TaskStateUpdateInput
    permissions: set[Permission] = set()

    def __init__(self, task_state_id: str):
        self._task_state_id = task_state_id

    async def run(self, args: TaskStateUpdateInput, ctx: ToolContext) -> ToolResult:
        try:
            result = await asyncio.to_thread(
                apply_task_state_update,
                self._task_state_id,
                ctx.execution_id,
                args.model_dump(exclude_unset=True),
            )
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        return ToolResult(content=json.dumps(result, ensure_ascii=False))
