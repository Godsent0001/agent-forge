"""Persistent project-local Python environments and dependency installation.

The environment lives inside the project's shared workspace, so Python execution
and shell-based application runs can use the same installed dependencies.
Package installation is a network/subprocess capability and is approval-gated.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.contracts.tools import Permission, Tool, ToolContext, ToolError, ToolResult

WALL_CLOCK_TIMEOUT_SECONDS = 300
MAX_OUTPUT_CHARS = 8000
_PACKAGE_SPEC = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,100}(?:\[[A-Za-z0-9_,.-]+\])?(?:[<>=!~]{1,2}[A-Za-z0-9.*+!_-]{1,80})?$"
)


class PythonEnvironmentInput(BaseModel):
    action: Literal["ensure", "install", "list"] = Field(
        description="ensure creates/reports the project virtual environment; install installs packages; list reports installed packages."
    )
    packages: list[str] = Field(
        default_factory=list,
        max_length=30,
        description="Package specifiers for install, e.g. ['requests>=2.31', 'pandas']. Do not include pip flags, URLs, or shell commands.",
    )


def _workspace_root(ctx: ToolContext) -> Path:
    root = Path(ctx.workspace.root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _venv_python(root: Path) -> Path:
    return root / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")


def _base_python() -> list[str]:
    """Find a compatible system Python for project-local virtual environments."""
    if not getattr(sys, "frozen", False):
        candidate = [sys.executable]
    elif os.name == "nt" and shutil.which("py"):
        # The Windows launcher selects an installed Python 3.11+ without relying
        # on whichever older Python happens to appear first on PATH.
        candidate = [shutil.which("py") or "py", "-3"]
    else:
        executable = shutil.which("python3") or shutil.which("python")
        candidate = [executable] if executable else []

    if candidate:
        try:
            result = subprocess.run(
                [*candidate, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
            )
            version_text = (result.stdout or result.stderr).strip()
            match = re.search(r"Python (\d+)\.(\d+)", version_text)
            if result.returncode == 0 and match and (int(match.group(1)), int(match.group(2))) >= (3, 11):
                return candidate
        except (OSError, subprocess.SubprocessError):
            pass

    raise ToolError(
        "AgentForge needs Python 3.11 or newer to create a project environment, but a compatible "
        "installation was not found. Install Python 3.11+ from https://www.python.org/downloads/ "
        "and enable the Python launcher or add Python to PATH, then retry."
    )

async def _run(command: list[str], *, cwd: Path) -> tuple[int, str]:
    env = {
        key: value for key, value in os.environ.items()
        if not any(marker in key.upper() for marker in ("_API_KEY", "_TOKEN", "_SECRET", "PASSWORD", "PASSWD"))
    }
    if os.name == "nt":
        env["PYTHONUTF8"] = "1"
    try:
        proc = await asyncio.create_subprocess_exec(
            *command, cwd=str(cwd), env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        try:
            output, _ = await asyncio.wait_for(proc.communicate(), timeout=WALL_CLOCK_TIMEOUT_SECONDS)
        except asyncio.TimeoutError as exc:
            proc.kill()
            await proc.wait()
            raise ToolError(f"Python environment command exceeded {WALL_CLOCK_TIMEOUT_SECONDS}s.") from exc
        except asyncio.CancelledError:
            proc.kill()
            await proc.wait()
            raise
    except OSError as exc:
        raise ToolError(f"Could not start Python environment command: {exc}") from exc
    text = output.decode("utf-8", errors="replace")
    if len(text) > MAX_OUTPUT_CHARS:
        text = text[:MAX_OUTPUT_CHARS] + "\n…[output truncated]"
    return proc.returncode or 0, text


class PythonEnvironmentTool(Tool):
    kind = "python_environment"
    default_description = (
        "Create or manage a persistent project-local Python virtual environment and install Python packages "
        "into it. Packages are stored under the current project workspace's .venv directory and can be used "
        "by the Python execution tool. Use this for dependency installation, not shell commands."
    )
    Input = PythonEnvironmentInput
    permissions: set[Permission] = {"subprocess", "net"}

    async def run(self, args: PythonEnvironmentInput, ctx: ToolContext) -> ToolResult:
        root = _workspace_root(ctx)
        python = _venv_python(root)
        if args.action == "install":
            if not args.packages:
                raise ToolError("Provide at least one package specifier to install.")
            invalid = [item for item in args.packages if not _PACKAGE_SPEC.fullmatch(item)]
            if invalid:
                raise ToolError(
                    "Invalid package specifier(s): " + ", ".join(repr(x) for x in invalid)
                    + ". Use package names and version constraints only; URLs and pip flags are not accepted."
                )

        if not python.is_file():
            if args.action == "list":
                raise ToolError("This project has no Python environment yet. Run action='ensure' first.")
            command = [*_base_python(), "-m", "venv", str(root / ".venv")]
            code, output = await _run(command, cwd=root)
            if code != 0:
                raise ToolError(f"Could not create the project virtual environment (exit {code}):\n{output}")
            if not python.is_file():
                raise ToolError("Virtual environment creation reported success, but its Python executable is missing.")

        if args.action == "ensure":
            return ToolResult(content=json.dumps({
                "status": "ready",
                "python": str(python),
                "workspace": str(root),
                "environment": ".venv",
                "dependency_manifest": "requirements.txt",
            }))

        if args.action == "list":
            code, output = await _run([str(python), "-m", "pip", "list", "--format=freeze"], cwd=root)
            if code != 0:
                raise ToolError(f"Could not list project packages (exit {code}):\n{output}")
            return ToolResult(content=output or "No packages installed.")

        code, output = await _run(
            [str(python), "-m", "pip", "install", "--disable-pip-version-check", *args.packages],
            cwd=root,
        )
        if code != 0:
            raise ToolError(f"Package installation failed (exit {code}):\n{output}")

        manifest = root / "requirements.txt"
        existing = manifest.read_text(encoding="utf-8").splitlines() if manifest.exists() else []
        merged = list(dict.fromkeys([line.strip() for line in existing if line.strip() and not line.lstrip().startswith("#")] + args.packages))
        temporary = manifest.with_suffix(".txt.tmp")
        temporary.write_text("\n".join(merged) + "\n", encoding="utf-8")
        temporary.replace(manifest)
        return ToolResult(content=json.dumps({
            "status": "installed",
            "packages": args.packages,
            "python": str(python),
            "manifest": "requirements.txt",
            "output": output,
        }, ensure_ascii=False))
