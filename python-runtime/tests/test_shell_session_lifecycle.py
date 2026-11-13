from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.tools import shell_sessions as shell_sessions_module


class _FakeProcess:
    returncode = None


@pytest.mark.asyncio
async def test_persistent_shell_process_cleanup_finishes_before_cancellation_propagates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    terminated = False

    async def terminate(_process: _FakeProcess) -> None:
        nonlocal terminated
        started.set()
        await release.wait()
        terminated = True

    monkeypatch.setattr(shell_sessions_module, "_terminate_process_tree", terminate)
    session = shell_sessions_module.ShellSession(
        session_id="shell-cancel-cleanup-test",
        project_id="project",
        cwd=tmp_path,
        process=_FakeProcess(),  # type: ignore[arg-type]
    )

    stopping = asyncio.create_task(session.stop())
    await started.wait()
    stopping.cancel()
    await asyncio.sleep(0)
    assert not stopping.done(), "cancellation must not interrupt process-tree termination"

    release.set()
    with pytest.raises(asyncio.CancelledError):
        await stopping

    assert terminated
