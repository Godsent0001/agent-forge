"""Tool-agnostic outcome classification for the RunnerCore feedback loop.

Tools expose a textual result at the model boundary, so the runner must distinguish
useful progress from explicit failures and common empty-result responses without
depending on a particular tool name.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolOutcome:
    succeeded: bool
    reason: str


_FAILURE_PREFIXES = (
    "error:",
    "failed:",
    "failure:",
)
_NO_PROGRESS_PATTERNS = (
    r"\bno results? found\b",
    r"\bno matches found\b",
    r"\b0 results?\b",
    r"\bno data (?:was )?found\b",
    r"\bnot found\b",
    r"\bunable to\b",
    r"\bcould not\b",
    r"\bfailed to\b",
    r"\btimed? out\b",
    r"\bunavailable\b",
    r"\baccess denied\b",
    r"\breturned an empty\b",
)


def classify_tool_outcome(result: str) -> ToolOutcome:
    """Classify the model-visible result independently of the tool's name."""
    text = (result or "").strip()
    lowered = text.lower()

    if not text:
        return ToolOutcome(False, "empty tool result")
    if lowered.startswith(_FAILURE_PREFIXES):
        return ToolOutcome(False, text[:240])

    # Avoid treating a successful diagnostic such as "no errors found" as failure.
    if re.search(r"\bno errors? found\b|\bwithout errors?\b", lowered):
        return ToolOutcome(True, "explicitly clean result")

    for pattern in _NO_PROGRESS_PATTERNS:
        if re.search(pattern, lowered):
            return ToolOutcome(False, text[:240])

    return ToolOutcome(True, "result returned")
