"""Conversation compaction logic for long chat histories."""
import logging
from typing import Any

logger = logging.getLogger(__name__)


def should_compact_conversation(
    history: list[Any],
    history_summary: str = "",
    context_window: int = 32000,
) -> bool:
    """Check if token length exceeds trigger threshold."""
    if len(history) <= 6:
        return False

    threshold = min(int(0.75 * context_window), 20000)
    total_chars = len(history_summary) + sum(
        len(getattr(m, "content", "") if hasattr(m, "content") else m.get("content", ""))
        for m in history
    )
    est_tokens = total_chars // 4

    return est_tokens >= threshold


async def compact_conversation(
    history: list[Any],
    history_summary: str = "",
    context_window: int = 32000,
    llm_complete_fn: Any = None,
) -> tuple[str, int]:
    """Compact older conversation turns into a new summary while keeping the last 6 messages verbatim."""
    if not should_compact_conversation(history, history_summary, context_window):
        return history_summary, 0

    older_messages = history[:-6]
    to_summarize = []
    if history_summary:
        to_summarize.append(f"Previous summary: {history_summary}")

    for msg in older_messages:
        role = getattr(msg, "role", None) or msg.get("role", "user")
        content = getattr(msg, "content", None) or msg.get("content", "")
        to_summarize.append(f"{role.upper()}: {content}")

    text_to_summarize = "\n".join(to_summarize)

    if not llm_complete_fn:
        fallback_summary = (history_summary + "\n[earlier messages omitted]").strip()
        return fallback_summary, len(older_messages)

    prompt = (
        "Summarize the following conversation history into a concise summary of at most 400 words.\n"
        "Preserve key facts, names, numbers, user decisions, constraints, and open tasks.\n\n"
        f"History to summarize:\n{text_to_summarize}"
    )

    try:
        turn = await llm_complete_fn([{"role": "user", "content": prompt}])
        new_summary = turn.text or history_summary
        return new_summary, len(older_messages)
    except Exception as e:
        logger.warning(f"Compaction call failed: {e}")
        fallback_summary = (history_summary + "\n[earlier messages omitted]").strip()
        return fallback_summary, len(older_messages)
