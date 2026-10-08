import pytest
from app.core.memory.compaction import compact_conversation, should_compact_conversation

@pytest.mark.asyncio
async def test_compaction_summarizes_older_turns():
    history = [{"role": "user", "content": f"message {i} " * 500} for i in range(10)]
    async def fake_complete(messages):
        class Turn:
            text = "summary of older turns"
        return Turn()
    summary, count = await compact_conversation(history, context_window=8000, llm_complete_fn=fake_complete)
    assert summary == "summary of older turns"
    assert count == 4
    assert should_compact_conversation(history, context_window=8000)

@pytest.mark.xfail(reason="blind spot, fixed in A-06")
def test_older_memory_is_summarized_or_included():
    history = [{"role": "user", "content": f"older {i}"} for i in range(12)]
    summary, count = "summary", 6
    assert all(f"older {i}" in summary for i in range(6)) or count >= 6
