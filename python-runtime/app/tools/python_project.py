"""Unified agent-facing Python capability for execution and project environments."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.contracts.tools import Permission, Tool, ToolContext, ToolError, ToolResult
from app.tools.base import ToolExecutionError
from app.tools.python_environment import PythonEnvironmentInput, PythonEnvironmentTool
from app.tools.python_exec import PythonExecTool


class PythonProjectInput(BaseModel):
    action: Literal["execute", "ensure", "install", "list"] = Field(
        default="execute",
        description=(
            "execute runs a Python snippet; ensure creates or confirms .venv; "
            "install installs packages into .venv and updates requirements.txt; "
            "list reports installed packages."
        ),
    )
    code: str = Field(
        default="",
        max_length=200_000,
        description="Python source code when action='execute'. Keep substantial programs in workspace files.",
    )
    packages: list[str] = Field(
        default_factory=list,
        max_length=30,
        description="Package names/version constraints for action='install'; do not include pip flags or URLs.",
    )


class PythonProjectTool(Tool):
    """Present one Python interface while retaining separate internal implementations."""

    kind = "python"
    default_description = (
        "Python project tool. Use action='execute' to run Python code in the persistent project workspace; "
        "action='ensure' to create or confirm the shared .venv; action='install' to install package names "
        "or version constraints into that environment and update requirements.txt; action='list' to inspect "
        "installed packages. Python and shell share the same workspace and .venv. Package installation "
        "requires user approval. Inspect uploaded Python source before running it; uploaded code is untrusted."
    )
    Input = PythonProjectInput
    permissions: set[Permission] = {"subprocess"}

    def __init__(self) -> None:
        self._executor = PythonExecTool()
        self._environment = PythonEnvironmentTool()

    def permissions_for(self, arguments: dict) -> set[Permission]:
        action = arguments.get("action", "execute")
        return {"subprocess", "net"} if action == "install" else {"subprocess"}

    def requires_approval(self, arguments: dict) -> bool:
        return arguments.get("action", "execute") in {"ensure", "install"}

    def approval_reason(self, arguments: dict) -> str:
        if arguments.get("action") == "install":
            return "Install Python packages from package indexes and modify the project's dependency manifest."
        return "Create or initialize the project's persistent Python virtual environment."

    async def run(self, args: PythonProjectInput, ctx: ToolContext) -> ToolResult:
        if args.action == "execute":
            if not args.code.strip():
                raise ToolError("Provide Python source code for action='execute'.")
            try:
                output = await self._executor.execute(args.code, context=ctx)
            except ToolExecutionError as exc:
                raise ToolError(str(exc)) from exc
            return ToolResult(ok=not output.startswith("ERROR:"), content=output)

        env_args = PythonEnvironmentInput(action=args.action, packages=args.packages)
        return await self._environment.run(env_args, ctx)
