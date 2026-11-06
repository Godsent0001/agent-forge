"""Typed local terminal capability for RunnerCore."""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar, Literal

from pydantic import BaseModel, Field

from app.contracts.tools import Permission, Tool, ToolContext, ToolError, ToolResult
from app.tools.base import ToolExecutionError
from app.tools.shell import ShellTool as LegacyShellTool
from app.tools.shell_sessions import shell_sessions


class ShellInput(BaseModel):
    action: Literal["run", "start", "write", "read", "stop"] = Field(
        default="run",
        description="run waits for a command; start creates a persistent terminal; write/read interact with it; stop terminates it.",
    )
    command: str = Field(
        default="",
        max_length=20_000,
        description="Command for run or start. Windows defaults to CMD; invoke powershell.exe -NoProfile -Command or pwsh for PowerShell. Unix uses the system shell.",
    )
    session_id: str = Field(default="", max_length=128, description="Session ID returned by start, required for write/read/stop.")
    input: str = Field(default="", max_length=20_000, description="Text or command to send to a persistent session for the write action.")
    max_output_chars: int = Field(default=12_000, ge=1, le=40_000, description="Maximum buffered output returned by read.")
    working_directory: str = Field(
        default="",
        max_length=1024,
        description=(
            "Optional absolute directory on the user's computer. Omit to use the persistent project workspace. "
            "Ordinary local project directories are available autonomously; clearly destructive system-wide "
            "commands still require approval."
        ),
    )
    timeout_seconds: int = Field(
        default=60,
        ge=1,
        le=300,
        description="Maximum command duration in seconds (1-300). Use a longer limit for installs or builds.",
    )


class ShellCapability(Tool):
    kind: ClassVar[str] = "shell"
    default_description: ClassVar[str] = (
        "Run a command in the user's local terminal on this computer. By default, commands run in the "
        "persistent AgentForge project workspace and can create files, run tests, invoke Python/Node tools, "
        "and inspect local project state. Set working_directory to an absolute local path to work elsewhere "
        "on this computer; ordinary work there is autonomous. Use action=start for long-running servers or "
        "processes, then action=read/write/stop with the returned session_id to manage that same terminal. "
        "On Windows CMD is the default; use powershell.exe or pwsh for PowerShell commands. "
        "Use action=run for commands that should finish and return output. This is terminal access, not "
        "graphical desktop control. Commands run with the "
        "current user's OS permissions and are not a full security sandbox."
    )
    Input = ShellInput
    permissions: set[Permission] = {"subprocess"}

    def __init__(self) -> None:
        self._implementation = LegacyShellTool()

    def requires_approval(self, arguments: dict) -> bool:
        # Local directories are part of the user's delegated computer-use scope.
        # Gate only commands that can damage the operating system or broadly destroy data.
        action = str(arguments.get("action", "run")).strip().casefold()
        command = str(
            arguments.get("input", "") if action == "write" else arguments.get("command", "")
        ).strip()
        dangerous_patterns = (
            r"\b(sudo\s+)?rm\s+-[^\n]*r[^\n]*f",
            r"\b(del|erase)\s+/(?:s|q).*",
            r"\b(rmdir|rd)\s+/(?:s|q)",
            r"\b(rm|del|erase|remove-item)\b[^\n]*(?:\.env|credentials|secrets|id_rsa|id_ed25519|\.pem|\.key|\.db|\.sqlite)",
            r"\b(format|diskpart|shutdown|restart-computer|stop-computer)\b",
            r"\b(remove-item|clear-disk)\b.*(?:-recurse|-force)",
            r"\b(reg\s+delete|reg\s+add)\b",
            r"\b(sudo\s+)?(mkfs|fdisk|parted|dd)\b",
            r"\b(sudo\s+)?(userdel|usermod|passwd|iptables|ufw)\b",
            r"\b(sudo\s+)?(systemctl|service)\s+(stop|disable|mask)",
        )
        return any(re.search(pattern, command, re.IGNORECASE) for pattern in dangerous_patterns)

    def approval_reason(self, arguments: dict) -> str:
        action = str(arguments.get("action", "run")).strip().casefold()
        command = str(
            arguments.get("input", "") if action == "write" else arguments.get("command", "")
        ).strip()
        directory = str(arguments.get("working_directory", "")).strip()
        return (
            "This command may perform a destructive or system-wide operation. "
            f"Command: {command[:240]} · Working directory: {directory or 'project workspace'}"
        )

    async def run(self, args: ShellInput, ctx: ToolContext) -> ToolResult:
        if args.action in {"write", "read", "stop"}:
            if not args.session_id.strip():
                raise ToolError(f"The {args.action} action requires session_id.")
            try:
                session = await shell_sessions.get(args.session_id.strip(), ctx.project_id)
                if args.action == "write":
                    if not args.input.strip():
                        raise ToolError("The write action requires non-empty input.")
                    await session.write(args.input)
                    return ToolResult(content=f"Sent input to terminal session {args.session_id}.")
                if args.action == "read":
                    output = await session.read(args.max_output_chars)
                    return ToolResult(content=f"Terminal session {args.session_id} ({session.cwd}):\n{output}")
                await shell_sessions.stop(args.session_id.strip(), ctx.project_id)
                return ToolResult(content=f"Stopped terminal session {args.session_id}.")
            except ValueError as exc:
                raise ToolError(str(exc)) from exc
            except (OSError, RuntimeError) as exc:
                raise ToolError(f"Terminal session operation failed: {exc}", retryable=True) from exc

        if not args.command.strip():
            raise ToolError(f"The {args.action} action requires a non-empty command.")
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
            timeout_seconds=args.timeout_seconds,
        )
        if args.action == "start":
            try:
                session = await shell_sessions.start(
                    project_id=ctx.project_id,
                    cwd=cwd,
                    command=args.command,
                )
            except (OSError, RuntimeError) as exc:
                raise ToolError(f"Could not start persistent terminal session: {exc}", retryable=True) from exc
            return ToolResult(content=(
                f"Started persistent terminal session.\n"
                f"session_id: {session.session_id}\n"
                f"working_directory: {cwd}\n"
                f"process_id: {session.process.pid}\n"
                "Use action=read to inspect output, action=write to send more commands, "
                "and action=stop to terminate this process."
            ))

        try:
            output = await self._implementation.execute(args.command, context=shell_context)
        except ToolExecutionError as exc:
            raise ToolError(str(exc), retryable=True) from exc
        return ToolResult(content=output)
