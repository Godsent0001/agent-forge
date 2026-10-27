"""Workspace-scoped shell execution with bounded output and a saved full log.

Shell access is a subprocess capability and is permission-gated by the v2
legacy-tool adapter. This is not an OS sandbox; only attach it to trusted agents.
"""
from __future__ import annotations

import asyncio
import os
import re
import signal
import subprocess
from pathlib import Path
from typing import Any

from app.tools.base import Tool, ToolExecutionError

WALL_CLOCK_TIMEOUT_SECONDS = 30
MAX_CAPTURE_BYTES = 1_000_000
MAX_OUTPUT_CHARS = 10_000
HEAD_CHARS = 4_000
TAIL_CHARS = 4_000


async def _read_bounded(stream: asyncio.StreamReader, limit: int) -> tuple[bytes, bool]:
    chunks: list[bytes] = []
    kept = 0
    truncated = False
    while True:
        chunk = await stream.read(8192)
        if not chunk:
            break
        remaining = limit - kept
        if remaining > 0:
            chunks.append(chunk[:remaining])
            kept += min(len(chunk), remaining)
        if len(chunk) > max(remaining, 0):
            truncated = True
    return b"".join(chunks), truncated


def _safe_environment() -> dict[str, str]:
    """Keep basic process variables but do not leak provider credentials to commands."""
    blocked = ("_API_KEY", "_TOKEN", "_SECRET", "PASSWORD", "PASSWD")
    env = {
        key: value for key, value in os.environ.items()
        if not any(marker in key.upper() for marker in blocked)
    }
    return env


async def _terminate_process_tree(proc: asyncio.subprocess.Process) -> None:
    """Stop the shell and its descendants, even when the caller is cancelled."""
    if os.name == "nt":
        # taskkill /T is required on Windows because killing cmd.exe alone can
        # leave commands it launched running after the execution was stopped.
        try:
            killer = await asyncio.create_subprocess_exec(
                "taskkill", "/PID", str(proc.pid), "/T", "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(killer.wait(), timeout=5)
        except (OSError, asyncio.TimeoutError):
            pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=2)
        except asyncio.TimeoutError:
            if proc.returncode is None:
                proc.kill()
            await proc.wait()
        return

    # Unix shell processes are started in their own session/process group.
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        await asyncio.wait_for(proc.wait(), timeout=1)
    except asyncio.TimeoutError:
        pass
    # Kill remaining descendants even if the shell parent already exited.
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    if proc.returncode is None:
        await proc.wait()


async def _cancel_reader_tasks(*tasks: asyncio.Task) -> None:
    for task in tasks:
        if not task.done():
            task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def _format_excerpt(text: str, truncated: bool) -> str:
    if not truncated and len(text) <= MAX_OUTPUT_CHARS:
        return text
    if len(text) <= MAX_OUTPUT_CHARS:
        return text[:MAX_OUTPUT_CHARS] + "\n…[output truncated; full captured log saved]"
    head = text[:HEAD_CHARS]
    tail = text[-TAIL_CHARS:]
    return (
        f"{head}\n\n…[middle omitted; {len(text) - len(head) - len(tail)} characters omitted]…\n\n"
        f"{tail}\n…[output truncated; full captured log saved]"
    )


class ShellTool(Tool):
    name = "shell"
    description = (
        "Run a CMD/PowerShell command on Windows or a shell command on Unix in the "
        "persistent project workspace. Returns bounded output, exit code, and absolute paths for files/logs."
    )

    async def execute(self, input: str, *, context: Any) -> str:
        command_text = input.strip()
        if not command_text:
            raise ToolExecutionError("shell requires a non-empty command")

        workspace = getattr(context, "workspace", None)
        root = getattr(workspace, "root", None)
        if root is None:
            raise ToolExecutionError("shell requires a run workspace")
        cwd = Path(root).resolve()
        cwd.mkdir(parents=True, exist_ok=True)

        if os.name == "nt":
            comspec = os.environ.get("COMSPEC", "cmd.exe")
            command = [comspec, "/d", "/s", "/c", command_text]
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        else:
            command = ["/bin/sh", "-lc", command_text]
            creationflags = 0

        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(cwd),
                env=_safe_environment(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=creationflags,
                start_new_session=(os.name != "nt"),
            )
            stdout_task = None
            stderr_task = None
            try:
                stdout_task = asyncio.create_task(_read_bounded(proc.stdout, MAX_CAPTURE_BYTES))
                stderr_task = asyncio.create_task(_read_bounded(proc.stderr, MAX_CAPTURE_BYTES))
                (stdout, stdout_cut), (stderr, stderr_cut) = await asyncio.wait_for(
                    asyncio.gather(stdout_task, stderr_task),
                    timeout=WALL_CLOCK_TIMEOUT_SECONDS,
                )
                await proc.wait()
            except asyncio.CancelledError:
                await _terminate_process_tree(proc)
                await _cancel_reader_tasks(*(task for task in (stdout_task, stderr_task) if task is not None))
                raise
            except asyncio.TimeoutError as exc:
                await _terminate_process_tree(proc)
                await _cancel_reader_tasks(*(task for task in (stdout_task, stderr_task) if task is not None))
                raise ToolExecutionError(
                    f"shell command exceeded the {WALL_CLOCK_TIMEOUT_SECONDS}s wall-clock limit"
                ) from exc
        except ToolExecutionError:
            raise
        except OSError as exc:
            raise ToolExecutionError(f"could not start shell command: {exc}") from exc

        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")
        combined = (
            f"Command: {command_text}\nExit code: {proc.returncode}\n"
            f"STDOUT:\n{stdout_text}\nSTDERR:\n{stderr_text}"
        )
        truncated = stdout_cut or stderr_cut
        log_path = None
        try:
            span_id = re.sub(r"[^A-Za-z0-9_-]", "_", str(getattr(context, "span_id", "output")))[:64] or "output"
            result_path = cwd / ".results" / f"shell-{span_id}.txt"
            result_path.parent.mkdir(parents=True, exist_ok=True)
            result_path.write_text(combined, encoding="utf-8")
            log_path = result_path.relative_to(cwd).as_posix()
        except (OSError, ValueError):
            # Output remains available in the returned excerpt if artifact storage fails.
            pass

        excerpt = _format_excerpt(combined, truncated or len(combined) > MAX_OUTPUT_CHARS)
        status = f"Exit code: {proc.returncode}"
        if log_path:
            status += f"\nFull captured output: {cwd / log_path}"
        if truncated:
            status += "\nCapture limit reached; output beyond the capture cap was discarded."
        return f"Project workspace: {cwd}\n{status}\n\n{excerpt}"
