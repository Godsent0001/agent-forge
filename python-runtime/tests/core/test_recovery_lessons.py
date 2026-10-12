import pytest

from app.core.lessons import InMemoryLessonStore, reflect_on_signal


@pytest.mark.asyncio
async def test_recovery_lesson_is_generic_and_deduplicated():
    store = InMemoryLessonStore()

    first = await reflect_on_signal(
        agent_id="agent-1",
        execution_id="run-1",
        error_message="API_KEY=secret-value request failed",
        recovered_output="A later tool call succeeded",
        store=store,
    )
    second = await reflect_on_signal(
        agent_id="agent-1",
        execution_id="run-1",
        error_message="same failure",
        recovered_output="same successful output",
        store=store,
    )

    assert len(first) == 1
    assert second == []
    assert "secret-value" not in first[0].text
    assert (await store.active("agent-1", limit=10)) == first
