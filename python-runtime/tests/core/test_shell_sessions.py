from __future__ import annotations

import asyncio
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.tools.shell_capability import ShellCapability, ShellInput


async def _read_until(tool: ShellCapability, ctx, session_id: str, expected: str) -> str:
    output = ""
    for _ in range(60):
        result = await tool.run(
            ShellInput(action="read", session_id=session_id, max_output_chars=4000),
            ctx,
        )
        output += result.content
        if expected in output:
            return output
        await asyncio.sleep(0.05)
    raise AssertionError(f"Expected terminal output {expected!r}; received: {output!r}")


@pytest.mark.asyncio
async def test_persistent_terminal_can_read_write_and_stop(tmp_path: Path):
    tool = ShellCapability()
    ctx = SimpleNamespace(
        execution_id="session-run",
        project_id="session-project",
        span_id="session-span",
        workspace=SimpleNamespace(root=tmp_path),
        cancel=None,
        config={},
    )
    started = await tool.run(
        ShellInput(action="start", command="echo session-ready"),
        ctx,
    )
    match = re.search(r"session_id:\s*([0-9a-f-]+)", started.content)
    assert match, started.content
    session_id = match.group(1)

    try:
        first = await _read_until(tool, ctx, session_id, "session-ready")
        assert "session-ready" in first

        await tool.run(
            ShellInput(action="write", session_id=session_id, input="echo live-input"),
            ctx,
        )
        second = await _read_until(tool, ctx, session_id, "live-input")
        assert "live-input" in second

        stopped = await tool.run(ShellInput(action="stop", session_id=session_id), ctx)
        assert "Stopped terminal session" in stopped.content
    finally:
        try:
            await tool.run(ShellInput(action="stop", session_id=session_id), ctx)
        except Exception:
            pass


@pytest.mark.asyncio
async def test_terminal_sessions_are_scoped_to_the_project(tmp_path: Path):
    tool = ShellCapability()
    ctx = SimpleNamespace(
        execution_id="session-run-2",
        project_id="session-project-a",
        span_id="session-span-2",
        workspace=SimpleNamespace(root=tmp_path),
        cancel=None,
        config={},
    )
    started = await tool.run(ShellInput(action="start", command="echo ready"), ctx)
    session_id = re.search(r"session_id:\s*([0-9a-f-]+)", started.content).group(1)
    try:
        other_project = SimpleNamespace(**{
            **ctx.__dict__,
            "project_id": "session-project-b",
        })
        with pytest.raises(Exception, match="not found in this project"):
            await tool.run(ShellInput(action="read", session_id=session_id), other_project)
    finally:
        await tool.run(ShellInput(action="stop", session_id=session_id), ctx)
