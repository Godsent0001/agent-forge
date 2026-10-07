"""Safety and validation checks for extracted candidate memories."""
import re
from typing import Sequence
from app.contracts.memory import MemoryCandidate, MemoryItem


INSTRUCTION_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous\s+)?instructions", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"call\s+the\s+.*tool", re.IGNORECASE),
    re.compile(r"send\s+.*to", re.IGNORECASE),
    re.compile(r"you\s+are\s+now", re.IGNORECASE),
]

SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),
    re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]{20,}"),
    re.compile(r"[a-fA-F0-9]{32,64}"),
]

URL_PATTERN = re.compile(r"https?://[^\s]+")


def validate_and_filter_candidate(
    candidate: MemoryCandidate,
    user_messages: Sequence[str],
    existing_items: Sequence[MemoryItem] = (),
) -> bool:
    """Validate a memory candidate against safety, evidence, length, and deduplication rules."""
    # 1. Text length check
    text = candidate.text.strip()
    if not text or len(text) > 200:
        return False

    # 2. Secret and URL filters
    for pat in SECRET_PATTERNS:
        if pat.search(text):
            return False
    if URL_PATTERN.search(text):
        return False

    # 3. Instruction injection pattern filter
    for pat in INSTRUCTION_INJECTION_PATTERNS:
        if pat.search(text):
            return False

    # 4. Evidence check: evidence must appear in user messages of this run
    evidence = candidate.evidence.strip().lower()
    if not evidence:
        return False

    evidence_matched = False
    for u_msg in user_messages:
        if evidence in u_msg.lower():
            evidence_matched = True
            break
    if not evidence_matched:
        return False

    # 5. Deduplication check (normalized Jaccard overlap)
    norm_candidate = set(text.lower().split())
    for item in existing_items:
        if item.status != "active":
            continue
        norm_item = set(item.text.lower().split())
        if not norm_candidate or not norm_item:
            continue
        intersection = len(norm_candidate.intersection(norm_item))
        union = len(norm_candidate.union(norm_item))
        jaccard = intersection / max(1, union)
        if jaccard >= 0.8:
            return False

    return True
