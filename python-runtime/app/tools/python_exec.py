"""Execute snippets in a restricted subprocess, not in the application process.

Limits: CPU time, best-effort address-space limits, wall-clock time, a minimal
environment, and bounded captured output. This is not a full OS sandbox: code
can still read files available to the current user and access the network.
DNS rebinding is a known limitation of outbound URL validation.
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

if os.name != "nt":
    import resource

from app.tools.base import Tool, ToolExecutionError
from app.tools.shell import _terminate_process_tree

CPU_TIME_LIMIT_SECONDS = 30
WALL_CLOCK_TIMEOUT_SECONDS = 60
MEMORY_LIMIT_BYTES = 1024 * 1024 * 1024
MAX_OUTPUT_CHARS = 10_000
MAX_CAPTURE_BYTES = MAX_OUTPUT_CHARS * 4


def _limit_resources() -> None:
    """Apply best-effort POSIX limits in the child process."""
    for limit_name, limits in (
        ("RLIMIT_CPU", (CPU_TIME_LIMIT_SECONDS, CPU_TIME_LIMIT_SECONDS)),
        ("RLIMIT_AS", (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES)),
        ("RLIMIT_NPROC", (0, 0)),
    ):
        limit = getattr(resource, limit_name, None)
        if limit is None:
            continue
        try:
            resource.setrlimit(limit, limits)
        except (OSError, ValueError):
            if limit_name != "RLIMIT_AS":
                raise


def _strip_markdown_fence(source: str) -> str:
    """Remove one surrounding Markdown code fence, if present."""
    match = re.match(
        r"^\s*```(?:python|py)?[ \t]*\r?\n(.*?)\r?\n```[ \t]*$",
        source,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return match.group(1) if match else source


def _filtered_path() -> str:
    """Preserve the user's system PATH while excluding activated project venvs."""
    entries = []
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        parts = {part.casefold() for part in Path(entry).parts}
        if ".venv" in parts or "venv" in parts or "virtualenv" in parts:
            continue
        entries.append(entry)
    if os.name == "nt":
        system_root = os.environ.get("SYSTEMROOT") or os.environ.get("SystemRoot")
        if system_root:
            system32 = str(Path(system_root) / "System32")
            if system32 not in entries:
                entries.insert(0, system32)
    return os.pathsep.join(entries)


def _resolve_shared_python_command() -> list[str]:
    """Find the user's shared Python interpreter, never a project-local venv."""
    explicit = os.environ.get("AGENTFORGE_PYTHON_EXECUTABLE", "").strip()
    if explicit:
        executable = Path(explicit).expanduser()
        if not executable.is_file():
            raise ToolExecutionError(
                f"AGENTFORGE_PYTHON_EXECUTABLE points to a missing file: {executable}"
            )
        return [str(executable.resolve())]

    search_path = _filtered_path()
    names = ("python.exe", "python3.exe", "python") if os.name == "nt" else ("python3", "python")
    for name in names:
        executable = shutil.which(name, path=search_path)
        if executable:
            return [executable]

    if os.name == "nt":
        launcher = shutil.which("py.exe", path=search_path) or shutil.which("py", path=search_path)
        if launcher:
            return [launcher, "-3"]

    raise ToolExecutionError(
        "No shared system Python interpreter was found. Install Python 3.11 or newer and add it to PATH, "
        "or set AGENTFORGE_PYTHON_EXECUTABLE to the full path of python.exe. AgentForge does not create "
        "or silently select project virtual environments."
    )


def _safe_environment(workspace_root: Path | None = None) -> dict[str, str]:
    """Preserve normal user environment variables but never leak credentials or inherit a venv."""
    blocked_markers = ("API_KEY", "_TOKEN", "_SECRET", "PASSWORD", "PASSWD")
    blocked_names = {"VIRTUAL_ENV", "PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP"}
    env = {
        key: value for key, value in os.environ.items()
        if key.upper() not in blocked_names
        and not any(marker in key.upper() for marker in blocked_markers)
    }
    env["PATH"] = _filtered_path()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if workspace_root is not None:
        env["PYTHONPATH"] = str(workspace_root)
    return env


async def _read_bounded(stream: asyncio.StreamReader, limit: int = MAX_CAPTURE_BYTES) -> tuple[bytes, bool]:
    """Drain a child pipe but retain only a bounded amount in memory."""
    chunks: list[bytes] = []
    kept = 0
    truncated = False
    while True:
        chunk = await stream.read(8192)
        if not chunk:
            break
        remaining = limit - kept
        if remaining > 0:
            take = chunk[:remaining]
            chunks.append(take)
            kept += len(take)
        if len(chunk) > max(remaining, 0):
            truncated = True
    return b"".join(chunks), truncated


def _decode_bounded(raw: bytes, truncated: bool) -> str:
    value = raw.decode("utf-8", errors="replace")
    if len(value) > MAX_OUTPUT_CHARS:
        value = value[:MAX_OUTPUT_CHARS]
        truncated = True
    return value + ("…[truncated]" if truncated else "")


class PythonExecTool(Tool):
    name = "python"
    description = "Execute a short Python snippet in a restricted subprocess."

    async def execute(self, input: str, *, context: Any) -> str:
        script = _strip_markdown_fence(input)
        workspace = getattr(context, "workspace", None)
        workspace_root = getattr(workspace, "root", None)
        owned_tmp = workspace_root is None
        if owned_tmp:
            tmp_dir = tempfile.mkdtemp(prefix="agentforge-py-")
            root = Path(tmp_dir).resolve()
        else:
            root = Path(workspace_root).resolve()
            root.mkdir(parents=True, exist_ok=True)
            tmp_dir = tempfile.mkdtemp(prefix="snippet-", dir=str(root / ".agentforge")) if (root / ".agentforge").is_dir() else ""
            if not tmp_dir:
                (root / ".agentforge").mkdir(parents=True, exist_ok=True)
                tmp_dir = tempfile.mkdtemp(prefix="snippet-", dir=str(root / ".agentforge"))
        script_path = os.path.join(tmp_dir, "snippet.py")
        proc = None
        try:
            with open(script_path, "w", encoding="utf-8") as handle:
                handle.write(script)

            # Execute with the user's shared/system Python, not the backend's
            # bundled interpreter or any project-local virtual environment.
            command = [*_resolve_shared_python_command(), script_path]

            kwargs: dict[str, Any] = {
                "cwd": str(root),
                "env": _safe_environment(root if not owned_tmp else None),
                "stdout": asyncio.subprocess.PIPE,
                "stderr": asyncio.subprocess.PIPE,
            }
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            else:
                kwargs["preexec_fn"] = _limit_resources
                kwargs["start_new_session"] = True

            proc = await asyncio.create_subprocess_exec(*command, **kwargs)
            stdout_task = asyncio.create_task(_read_bounded(proc.stdout))
            stderr_task = asyncio.create_task(_read_bounded(proc.stderr))
            try:
                (stdout, stdout_truncated), (stderr, stderr_truncated) = await asyncio.wait_for(
                    asyncio.gather(stdout_task, stderr_task), timeout=WALL_CLOCK_TIMEOUT_SECONDS
                )
                await proc.wait()
            except asyncio.TimeoutError as exc:
                await _terminate_process_tree(proc)
                for task in (stdout_task, stderr_task):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
                raise ToolExecutionError(
                    f"python tool exceeded {WALL_CLOCK_TIMEOUT_SECONDS}s wall-clock limit"
                ) from exc
            except asyncio.CancelledError:
                await _terminate_process_tree(proc)
                for task in (stdout_task, stderr_task):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
                raise

            out_text = _decode_bounded(stdout, stdout_truncated)
            err_text = _decode_bounded(stderr, stderr_truncated)
            if proc.returncode != 0:
                detail = err_text or out_text or "no error output"
                raise ToolExecutionError(f"python snippet exited {proc.returncode}: {detail}")
            return out_text
        except ToolExecutionError:
            raise
        except OSError as exc:
            raise ToolExecutionError(f"python tool could not start: {exc}") from exc
        finally:
            if proc is not None and proc.returncode is None:
                await _terminate_process_tree(proc)
            shutil.rmtree(tmp_dir, ignore_errors=True)
