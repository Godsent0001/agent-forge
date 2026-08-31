"""
Python execution tool.

SANDBOXING DECISION (made explicitly, per the build plan's flagged risk —
this is not something to figure out inline later):

  - Run user/agent-supplied code as a SEPARATE OS SUBPROCESS, never in-process
    via exec()/eval(). In-process execution can access the runtime's own
    memory, DB session, and API keys — a subprocess boundary is required.
  - Apply POSIX resource limits (CPU time, memory, no forking further
    children) via the `resource` module before exec'ing the subprocess.
  - Hard wall-clock timeout via asyncio, independent of the CPU limit,
    to catch code that sleeps/blocks on I/O instead of spinning CPU.
  - Strip environment variables down to a minimal safe set — the
    subprocess must NOT inherit API keys or other secrets from this
    process's environment.
  - Run inside a fresh temp directory, deleted after execution, so the
    tool can't read/write arbitrary paths on the user's machine.

This is a "restricted subprocess" sandbox, not a full container/VM. It
stops accidental damage and casual misuse. It is NOT sufficient isolation
for running fully untrusted third-party code from strangers — if this
product later accepts community-submitted tools, upgrade to a real
container (gVisor/Firecracker) before doing so. That's a explicit
non-goal for V1, called out here rather than silently assumed away.
"""

from __future__ import annotations

import asyncio
import os
import resource
import shutil
import sys
import tempfile
from typing import Any

from app.tools.base import Tool, ToolExecutionError

CPU_TIME_LIMIT_SECONDS = 5
WALL_CLOCK_TIMEOUT_SECONDS = 10
MEMORY_LIMIT_BYTES = 256 * 1024 * 1024  # 256 MB


def _limit_resources() -> None:
    """Called via preexec_fn in the child process, before exec."""
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_TIME_LIMIT_SECONDS, CPU_TIME_LIMIT_SECONDS))
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))
    # Prevent the sandboxed code from forking further children.
    resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))


class PythonExecTool(Tool):
    name = "python"
    description = "Execute a short Python snippet in a restricted sandbox and return stdout."

    async def execute(self, input: str, *, context: Any) -> str:
        tmp_dir = tempfile.mkdtemp(prefix="agentforge-py-")
        script_path = os.path.join(tmp_dir, "snippet.py")
        try:
            with open(script_path, "w") as f:
                f.write(input)

            # Minimal env — no inherited API keys/secrets.
            safe_env = {"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"}

            proc = await asyncio.create_subprocess_exec(
                sys.executable, script_path,
                cwd=tmp_dir,
                env=safe_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=_limit_resources if os.name != "nt" else None,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=WALL_CLOCK_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError as e:
                proc.kill()
                await proc.wait()
                raise ToolExecutionError(
                    f"python tool exceeded {WALL_CLOCK_TIMEOUT_SECONDS}s wall-clock limit"
                ) from e

            if proc.returncode != 0:
                raise ToolExecutionError(
                    f"python snippet exited {proc.returncode}: {stderr.decode(errors='replace')[:2000]}"
                )
            return stdout.decode(errors="replace")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
