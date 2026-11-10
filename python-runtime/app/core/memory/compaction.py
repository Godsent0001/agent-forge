"""Deterministic, bounded conversation compaction."""
from __future__ import annotations

import re
from typing import Any

_KEEP_RECENT_MESSAGES = 6
_IMPORTANT = re.compile(
    r"\b(decid(?:e|ed|ing)|must|should|never|always|prefer(?:s|red)?|"
    r"constraint|require(?:s|d)?|correct(?:ion|ed)?|actually|instead|"
    r"important|blocked|blocker|todo|next step|remaining|deadline|"
    r"failed|error|fixed|working|implemented|built|created|selected|"
    r"choose|chosen|agreed|do not|don't|cannot|can't|will|need to)\b",
    re.IGNORECASE,
)
_PATH_OR_REF = re.compile(
    r"(?:[A-Za-z]:\\\\[^\s,;]+|/(?:[\w.-]+/)+[\w.-]+|"
    r"\b(?:PR|pull request)\s*#?\d+|https?://\S+)",
    re.IGNORECASE,
)

def _field(message: Any, name: str, default: str = "") -> str:
    value = getattr(message, name, None)
    if value is None and isinstance(message, dict):
        value = message.get(name, default)
    return str(value or default)

def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()

def _extract_evidence(messages: list[Any]) -> list[str]:
    """Extract concise, attributable evidence without a model call."""
    evidence: list[str] = []
    for message in messages:
        role = _field(message, "role", "user").lower()
        content = _field(message, "content").strip()
        if not content:
            continue
        if role in {"tool", "function"} and not (_IMPORTANT.search(content) or _PATH_OR_REF.search(content)):
            continue
        sentences = re.split(r"(?<=[.!?])\s+|\n+", content)
        selected: list[str] = []
        for sentence in sentences:
            sentence = re.sub(r"\s+", " ", sentence).strip(" -\t")
            if not sentence:
                continue
            if role == "user" or _IMPORTANT.search(sentence) or _PATH_OR_REF.search(sentence):
                if len(sentence) > 420:
                    sentence = sentence[:417].rstrip() + "..."
                selected.append(sentence)
            if len(selected) >= 4:
                break
        evidence.extend(f"- [{role}] {sentence}" for sentence in selected)
    return evidence

def _bounded_summary(previous: str, new_evidence: list[str], budget_chars: int) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for line in [*previous.splitlines(), *new_evidence]:
        line = line.strip()
        if not line or line == "Conversation memory:":
            continue
        key = _normalise(line)
        if key not in seen:
            seen.add(key)
            lines.append(line)
    header = "Conversation memory:"
    kept: list[str] = []
    used = len(header) + 1
    for line in reversed(lines):
        if used + len(line) + 1 <= budget_chars:
            kept.append(line)
            used += len(line) + 1
    kept.reverse()
    return "\n".join([header, *kept])

def should_compact_conversation(history: list[Any], history_summary: str = "", context_window: int = 32000) -> bool:
    """Return whether history exceeds the bounded compaction threshold."""
    if len(history) <= _KEEP_RECENT_MESSAGES:
        return False
    threshold = min(int(0.75 * context_window), 20000)
    total_chars = len(history_summary) + sum(len(_field(message, "content")) for message in history)
    return total_chars // 4 >= threshold

async def compact_conversation(history: list[Any], history_summary: str = "", context_window: int = 32000, llm_complete_fn: Any = None) -> tuple[str, int]:
    """Compact older messages deterministically and keep the newest six verbatim.

    llm_complete_fn remains accepted for API compatibility but is never called.
    """
    if not should_compact_conversation(history, history_summary, context_window):
        return history_summary, 0
    older_messages = history[:-_KEEP_RECENT_MESSAGES]
    evidence = _extract_evidence(older_messages)
    budget_chars = max(800, min(6000, int(context_window * 4 * 0.10)))
    return _bounded_summary(history_summary, evidence, budget_chars), len(older_messages)
