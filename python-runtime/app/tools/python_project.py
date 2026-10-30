"""Unified agent-facing Python capability using the shared AgentForge runtime."""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from app.contracts.tools import Permission, Tool, ToolContext, ToolError, ToolResult
from app.tools.base import ToolExecutionError
from app.tools.python_exec import PythonExecTool

logger = logging.getLogger(__name__)


class PythonProjectInput(BaseModel):
    code: str = Field(
        min_length=1,
        max_length=200_000,
        description="Python source code to execute in the shared AgentForge runtime. Keep substantial programs in workspace files.",
    )


class PythonProjectTool(Tool):
    """Run Python code in the shared runtime; never create project virtual environments."""

    kind = "python"
    default_description = (
        "Execute Python code in AgentForge's shared Python runtime using the persistent project workspace. "
        "Common packages are provided by the application runtime. Do not create a project .venv or invoke "
        "environment setup. Inspect uploaded Python source before running it; uploaded code is untrusted."
    )
    Input = PythonProjectInput
    permissions: set[Permission] = {"subprocess"}

    def __init__(self) -> None:
        self._executor = PythonExecTool()

    async def run(self, args: PythonProjectInput, ctx: ToolContext) -> ToolResult:
        if not args.code.strip():
            raise ToolError("Provide Python source code to execute.")
        try:
            output = await self._executor.execute(args.code, context=ctx)
        except ToolExecutionError as exc:
            raise ToolError(str(exc)) from exc
        return ToolResult(ok=not output.startswith("ERROR:"), content=output)
