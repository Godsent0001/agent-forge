"""Execute snippets in a restricted subprocess, not in the application process.

Limits: CPU, address space where supported, wall-clock time, environment
inheritance, and captured output. This is not a full OS sandbox: code can still
read files available to the current user and access the network. DNS rebinding
is also a known limitation of the HTTP tool's URL validation.
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
import tempfile
from typing import Any

if os.name != "nt":
    import resource
import shutil

from app.tools.base import Tool, ToolExecutionError

CPU_TIME_LIMIT_SECONDS = 5
WALL_CLOCK_TIMEOUT_SECONDS = 10
MEMORY_LIMIT_BYTES = 256 * 1024 * 1024
MAX_OUTPUT_CHARS = 10_000


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
            # RLIMIT_AS is unreliable on macOS; retain other limits where possible.
            if limit_name != "RLIMIT_AS":
                raise


def _strip_markdown_fence(source: str) -> str:
    """Remove one surrounding Markdown code fence, if present."""
    match = re.match(
        r"^\\s*```(?:python|py)?[ \\t]*\\r?\\n(.*?)\\r?\\n```[ \\t]*$",
        source,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return match.group(1) if match else source


def _cap_output(value: str) -> str:
    if len(value) <= MAX_OUTPUT_CHARS:
        return value
    return value[:MAX_OUTPUT_CHARS] + "…[truncated]"


def _safe_environment() -> dict[str, str]:
    """Construct a small environment without inherited provider/API secrets."""
    path_parts = ["/usr/bin", "/bin"]
    if os.name == "nt":
        path_parts = []
        system_root = os.environ.get("SYSTEMROOT") or os.environ.get("SystemRoot")
        if system_root:
            path_parts.append(os.path.join(system_root, "System32"))
        path_parts.append(os.path.dirname(sys.executable))
        safe_env = {
            "PATH": os.pathsep.join(path_parts),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        for key in ("SYSTEMROOT", "TEMP", "TMP"):
            value = os.environ.get(key) or os.environ.get(key.lower())
            if value:
                safe_env[key] = value
        return safe_env
    return {"PATH": os.pathsep.join(path_parts), "PYTHONDONTWRITEBYTECODE": "1"}


class PythonExecTool(Tool):
    name = "python"
    description = "Execute a short Python snippet in a restricted subprocess."

    async def execute(self, input: str, *, context: Any) -> str:
        script = _strip_markdown_fence(input)
        tmp_dir = tempfile.mkdtemp(prefix="agentforge-py-")
        script_path = os.path.join(tmp_dir, "snippet.py")
        proc = None
        try:
            with open(script_path, "w", encoding="utf-8") as handle:
                handle.write(script)

            command = (
                [sys.executable, "--run-snippet", script_path]
                if getattr(sys, "frozen", False)
                else [sys.executable, script_path]
            )
            kwargs: dict[str, Any] = {
                "cwd": tmp_dir,
                "env": _safe_environment(),
                "stdout": asyncio.subprocess.PIPE,
                "stderr": asyncio.subprocess.PIPE,
            }
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            else:
                kwargs["preexec_fn"] = _limit_resources

            proc = await asyncio.create_subprocess_exec(*command, **kwargs)
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=WALL_CLOCK_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError as exc:
                proc.kill()
                await proc.wait()
                raise ToolExecutionError(
                    f"python tool exceeded {WALL_CLOCK_TIMEOUT_SECONDS}s wall-clock limit"
                ) from exc

            out_text = _cap_output(stdout.decode(errors="replace"))
            err_text = _cap_output(stderr.decode(errors="replace"))
            if proc.returncode != 0:
                detail = err_text or out_text or "no error output"
                raise ToolExecutionError(
                    f"python snippet exited {proc.returncode}: {detail}"
                )
            return out_text
        except ToolExecutionError:
            raise
        except OSError as exc:
            raise ToolExecutionError(f"python tool could not start: {exc}") from exc
        finally:
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.wait()
            shutil.rmtree(tmp_dir, ignore_errors=True)
