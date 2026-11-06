"""Unified agent-facing Python capability using the user shared system Python."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.tools import Permission, Tool, ToolContext, ToolError, ToolResult
from app.tools.base import ToolExecutionError
from app.tools.python_exec import PythonExecTool


class PythonProjectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(
        min_length=1,
        max_length=200_000,
        description="Python source code to execute with the user shared system Python interpreter. Keep substantial programs in workspace files.",
    )


class PythonProjectTool(Tool):
    """Run Python code in the user shared system interpreter; never create project virtual environments."""

    kind = "python"
    default_description = (
        "Execute Python code with the user's shared system Python interpreter in the persistent project workspace. "
        "Use packages installed in that shared interpreter. Do not create or activate project .venv environments. "
        "Inspect uploaded Python source before running it; uploaded code is untrusted."
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
