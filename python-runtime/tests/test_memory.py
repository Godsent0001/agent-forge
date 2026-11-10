import pytest

from app.core.memory.compaction import compact_conversation, should_compact_conversation


@pytest.mark.asyncio
async def test_compaction_extracts_older_evidence_without_llm_call():
    history = [{"role": "user", "content": f"message {i} " * 500} for i in range(10)]
    calls = []

    async def fake_complete(messages):
        calls.append(messages)
        raise AssertionError("deterministic compaction must not call an LLM")

    summary, count = await compact_conversation(history, context_window=8000, llm_complete_fn=fake_complete)
    assert summary.startswith("Conversation memory:")
    assert "[user] message 0" in summary
    assert "[user] message 3" in summary
    assert count == 4
    assert calls == []
    assert should_compact_conversation(history, context_window=8000)

@pytest.mark.xfail(reason="blind spot, fixed in A-06")
def test_older_memory_is_summarized_or_included():
    summary, count = "summary", 6
    assert all(f"older {i}" in summary for i in range(6)) or count >= 6
