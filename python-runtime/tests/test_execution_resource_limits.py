from __future__ import annotations

import asyncio

import pytest

from app.services.executions import ExecutionManager


@pytest.mark.asyncio
async def test_execution_manager_bounds_active_runs_and_prunes_finished_tasks() -> None:
    manager = ExecutionManager()
    first = asyncio.create_task(asyncio.sleep(60))
    second = asyncio.create_task(asyncio.sleep(60))
    manager.active = {"first": first, "second": second}

    with pytest.raises(RuntimeError, match="at most 2 active executions"):
        manager._ensure_execution_capacity()

    first.cancel()
    second.cancel()
    await asyncio.gather(first, second, return_exceptions=True)

    finished = asyncio.create_task(asyncio.sleep(0))
    await finished
    manager.active["finished"] = finished
    manager._ensure_execution_capacity()
    assert manager.active == {}
