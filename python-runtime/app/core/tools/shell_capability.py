"""Typed local terminal capability for RunnerCore."""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

from pydantic import BaseModel, Field

from app.contracts.tools import Permission, Tool, ToolContext, ToolError, ToolResult
from app.tools.base import ToolExecutionError
from app.tools.shell import ShellTool as LegacyShellTool


class ShellInput(BaseModel):
    command: str = Field(
        min_length=1,
        max_length=20_000,
        description="A CMD/PowerShell command on Windows or shell command on Unix.",
    )
    working_directory: str = Field(
        default="",
        max_length=1024,
        description=(
            "Optional directory on the user's computer. Omit to use the persistent project workspace. "
            "Relative paths are resolved inside the project workspace; absolute paths outside it require approval."
        ),
    )


class ShellCapability(Tool):
    kind: ClassVar[str] = "shell"
    default_description: ClassVar[str] = (
        "Run a command in the user's local terminal on this computer. By default, commands run in the "
        "persistent AgentForge project workspace and can create files, run tests, invoke Python/Node tools, "
        "and inspect local project state. Set working_directory to work in another local folder; that request "
        "requires approval. This is terminal access, not graphical desktop control. Commands run with the "
        "current user's OS permissions and are not a full security sandbox."
    )
    Input = ShellInput
    permissions: set[Permission] = {"subprocess"}

    def __init__(self) -> None:
        self._implementation = LegacyShellTool()

    def requires_approval(self, arguments: dict) -> bool:
        # Moving the working directory away from the default project workspace is
        # a meaningful increase in filesystem scope and always requires confirmation.
        return bool(str(arguments.get("working_directory", "")).strip())

    def approval_reason(self, arguments: dict) -> str:
        directory = str(arguments.get("working_directory", "")).strip()
        return f"Run a local terminal command with working directory: {directory}"

    async def run(self, args: ShellInput, ctx: ToolContext) -> ToolResult:
        project_root = Path(ctx.workspace.root).resolve()
        requested = args.working_directory.strip()
        try:
            if not requested:
                cwd = project_root
            else:
                candidate = Path(requested).expanduser()
                if candidate.is_absolute():
                    cwd = candidate.resolve(strict=True)
                else:
                    cwd = ctx.workspace.resolve(requested).resolve(strict=True)
                if not cwd.is_dir():
                    raise ToolError("The requested working directory is not a directory.")
                if not cwd.is_relative_to(project_root) and not candidate.is_absolute():
                    raise ToolError("Relative working directories must remain inside the project workspace.")
        except ToolError:
            raise
        except (OSError, ValueError, RuntimeError) as exc:
            raise ToolError(f"Could not resolve the requested working directory: {exc}") from exc

        # The underlying shell implementation only needs workspace.root and span_id.
        # Keep the original execution/project identity while making its cwd explicit.
        shell_context = SimpleNamespace(
            execution_id=ctx.execution_id,
            project_id=ctx.project_id,
            span_id=ctx.span_id,
            workspace=SimpleNamespace(root=cwd),
            cancel=ctx.cancel,
            config=ctx.config,
        )
        try:
            output = await self._implementation.execute(args.command, context=shell_context)
        except ToolExecutionError as exc:
            raise ToolError(str(exc), retryable=True) from exc
        return ToolResult(content=output)
