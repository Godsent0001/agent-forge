import pytest

from app.contracts.run import BudgetSpec
from app.core.budget import BudgetExceededError, BudgetTracker
from app.core.memory.compaction import (
    MAX_MESSAGE_CHARS,
    deterministic_summary,
    history_budget_chars,
    merge_history,
    split_for_budget,
    summarize_evicted,
)


def _turns(count: int, size: int = 400) -> list[dict[str, str]]:
    messages = []
    for index in range(count):
        messages.append({"role": "user", "content": f"question {index} " + "u" * size})
        messages.append({"role": "assistant", "content": f"answer {index} " + "a" * size})
    return messages


def test_history_budget_follows_the_model_context_window():
    assert history_budget_chars(8_000) < history_budget_chars(32_000) < history_budget_chars(200_000)
    # A large-context model is still capped so every tool-loop call stays affordable.
    assert history_budget_chars(1_000_000) == history_budget_chars(200_000)


def test_nothing_is_evicted_while_history_fits():
    messages = _turns(20, size=100)
    evicted, kept = split_for_budget(messages, history_budget_chars(32_000))
    assert evicted == []
    assert kept == messages  # 40 messages survive; the old limit was 8


def test_overflow_evicts_oldest_and_window_starts_on_a_user_turn():
    messages = _turns(30, size=1_000)
    budget = history_budget_chars(32_000)
    evicted, kept = split_for_budget(messages, budget)
    assert evicted and kept
    assert evicted + kept == messages
    assert kept[0]["role"] == "user"
    assert sum(len(m["content"]) for m in kept) <= budget
    assert len(kept) >= 4


def test_interim_assistant_messages_form_one_turn():
    merged = merge_history([
        {"role": "user", "content": "build it"},
        {"role": "assistant", "content": "Working on it."},
        {"role": "assistant", "content": "Done: created app.py"},
        {"role": "assistant", "content": "Done: created app.py"},
        {"role": "user", "content": "thanks"},
    ])
    assert [m["role"] for m in merged] == ["user", "assistant", "user"]
    assert merged[1]["content"] == "Working on it.\n\nDone: created app.py"


def test_long_message_keeps_its_beginning_and_its_conclusion():
    content = "START " + "x" * (MAX_MESSAGE_CHARS * 2) + " FINAL ANSWER"
    merged = merge_history([{"role": "assistant", "content": content}])
    assert len(merged[0]["content"]) <= MAX_MESSAGE_CHARS + 50
    assert merged[0]["content"].startswith("START")
    assert merged[0]["content"].endswith("FINAL ANSWER")


@pytest.mark.asyncio
async def test_summary_is_written_by_the_model_and_receives_the_previous_summary():
    calls = []

    async def fake_summarize(messages):
        calls.append(messages)
        return "UPDATED SUMMARY"

    summary, used_model = await summarize_evicted("Port is 5433.", _turns(2), fake_summarize)
    assert (summary, used_model) == ("UPDATED SUMMARY", True)
    assert "Port is 5433." in calls[0][1]["content"]
    assert "question 0" in calls[0][1]["content"] and "answer 1" in calls[0][1]["content"]


@pytest.mark.asyncio
async def test_failed_summary_call_falls_back_without_losing_everything():
    async def broken(_messages):
        raise RuntimeError("provider down")

    evicted = [
        {"role": "user", "content": "The database is Postgres 16 on port 5433."},
        {"role": "assistant", "content": "Configured Redis with a 300s TTL."},
    ]
    summary, used_model = await summarize_evicted("", evicted, broken)
    assert used_model is False
    assert "5433" in summary and "300s" in summary


def test_deterministic_fallback_is_bounded_and_drops_oldest_first():
    messages = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"Fact number {i} is {i * 7}."}
        for i in range(400)
    ]
    summary = deterministic_summary("", messages, budget_chars=1_000)
    assert len(summary) <= 1_000
    assert "Fact number 399" in summary and "Fact number 0 " not in summary


def test_prompt_limit_tracks_the_context_window_instead_of_a_fixed_cap():
    tracker = BudgetTracker(BudgetSpec())
    messages = [{"role": "system", "content": "x" * 80_000}]  # ~23k tokens: over the old 12k cap
    tracker.check_request(messages, context_window=200_000)
    with pytest.raises(BudgetExceededError, match="context window"):
        tracker.check_request(messages, context_window=16_000)
