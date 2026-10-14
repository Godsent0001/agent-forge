import asyncio

import pytest

from app.core.spans import span


@pytest.mark.asyncio
async def test_cancelled_span_is_marked_cancelled():
    events = []

    async def emit(event):
        events.append(event)

    with pytest.raises(asyncio.CancelledError):
        async with span(emit, kind="tool_call", name="slow_tool"):
            raise asyncio.CancelledError

    assert [event.type for event in events] == ["span_started", "span_ended"]
    assert events[-1].status == "cancelled"
