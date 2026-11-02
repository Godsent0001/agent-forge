from __future__ import annotations

import asyncio

import pytest

from app.services.executions import CancelTokenImpl


@pytest.mark.asyncio
async def test_live_stop_instruction_cancels_the_active_tool_without_cancelling_the_run():
    token = CancelTokenImpl()
    started = asyncio.Event()

    async def long_running_tool():
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(long_running_tool())
    token.register_tool("tool-call-1", task)
    await started.wait()

    instruction = "Stop the current command and use the new approach instead."
    token.enqueue_message(instruction)

    with pytest.raises(asyncio.CancelledError):
        await task

    assert token.cancelled is False
    assert token.drain_messages() == [instruction]


@pytest.mark.asyncio
async def test_live_status_message_does_not_stop_an_active_tool():
    token = CancelTokenImpl()
    started = asyncio.Event()

    async def long_running_tool():
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(long_running_tool())
    token.register_tool("tool-call-2", task)
    await started.wait()

    instruction = "Can you give me a quick status update?"
    token.enqueue_message(instruction)

    assert not task.done()
    assert token.drain_messages() == [instruction]

    assert token.stop_tool("tool-call-2") is True
    with pytest.raises(asyncio.CancelledError):
        await task
