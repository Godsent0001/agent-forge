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
import sys
import tempfile
from pathlib import Path
from typing import Any

if os.name != "nt":
    import resource

from app.tools.base import Tool, ToolExecutionError

CPU_TIME_LIMIT_SECONDS = 5
WALL_CLOCK_TIMEOUT_SECONDS = 10
MEMORY_LIMIT_BYTES = 256 * 1024 * 1024
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


def _safe_environment(workspace_root: Path | None = None) -> dict[str, str]:
    """Construct a small environment without inherited provider/API secrets."""
    if os.name == "nt":
        system_root = os.environ.get("SYSTEMROOT") or os.environ.get("SystemRoot")
        path_parts = [os.path.join(system_root, "System32")] if system_root else []
        path_parts.append(os.path.dirname(sys.executable))
        if workspace_root is not None:
            venv_cfg = workspace_root / ".venv" / "pyvenv.cfg"
            if venv_cfg.is_file():
                for line in venv_cfg.read_text(encoding="utf-8", errors="replace").splitlines():
                    key, separator, value = line.partition("=")
                    if separator and key.strip().casefold() == "home":
                        base_home = value.strip()
                        if base_home:
                            path_parts.append(base_home)
                            break
        env = {"PATH": os.pathsep.join(path_parts), "PYTHONDONTWRITEBYTECODE": "1"}
        for key in ("SYSTEMROOT", "TEMP", "TMP"):
            value = os.environ.get(key) or os.environ.get(key.lower())
            if value:
                env[key] = value
        if workspace_root is not None:
            env["PYTHONPATH"] = str(workspace_root)
        return env
    env = {"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"}
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

            venv_python = root / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
            if venv_python.is_file():
                command = [str(venv_python), script_path]
            elif getattr(sys, "frozen", False):
                command = [sys.executable, "--run-snippet", script_path]
            else:
                command = [sys.executable, script_path]

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

            proc = await asyncio.create_subprocess_exec(*command, **kwargs)
            try:
                stdout_task = asyncio.create_task(_read_bounded(proc.stdout))
                stderr_task = asyncio.create_task(_read_bounded(proc.stderr))
                (stdout, stdout_truncated), (stderr, stderr_truncated) = await asyncio.wait_for(
                    asyncio.gather(stdout_task, stderr_task), timeout=WALL_CLOCK_TIMEOUT_SECONDS
                )
                await proc.wait()
            except asyncio.TimeoutError as exc:
                proc.kill()
                await proc.wait()
                raise ToolExecutionError(
                    f"python tool exceeded {WALL_CLOCK_TIMEOUT_SECONDS}s wall-clock limit"
                ) from exc

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
                proc.kill()
                await proc.wait()
            shutil.rmtree(tmp_dir, ignore_errors=True)
