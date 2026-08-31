from __future__ import annotations

from typing import Any

from app.runtime.agent import RuntimeAgent
from app.runtime.context import ExecutionContext
from app.tools.base import Tool


class AgentTool(Tool):
    """
    Wraps a RuntimeAgent so a parent agent can call it exactly like any
    other Tool. This is the recursion seam: when the parent's loop calls
    tool.execute(), if `tool` happens to be one of these, execution
    re-enters RuntimeAgent.run() one level deeper via context.descend(),
    which is what enforces the depth limit and cycle guard.
    """

    def __init__(self, agent: RuntimeAgent, name: str, description: str):
        self.agent = agent
        self.name = name
        self.description = description

    async def execute(self, input: str, *, context: ExecutionContext) -> str:
        await context.emit("ChildAgentStarted", agent_name=self.agent.name)
        child_context = context.descend(self.agent.id)
        result = await self.agent.run(input, context=child_context)
        await context.emit("ChildAgentCompleted", agent_name=self.agent.name)
        return result
