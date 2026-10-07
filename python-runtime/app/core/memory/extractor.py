"""Inline memory extraction pass at the end of runs."""
import json
import logging
from typing import Any, Sequence
from app.contracts.graph import AgentSpec
from app.contracts.memory import MemoryCandidate, MemoryStore
from app.core.memory.safety import validate_and_filter_candidate

logger = logging.getLogger(__name__)

CUE_WORDS = {"remember", "from now on", "always", "never", "i prefer", "my ", "i am", "i'm", "i use"}


def should_trigger_extraction(
    spec: AgentSpec,
    user_messages: Sequence[str],
    used_tools: bool = False,
) -> bool:
    """Check if extraction gate conditions are satisfied."""
    if not spec.memory_enabled:
        return False

    if used_tools:
        return True

    full_text = " ".join(user_messages).lower()
    for cue in CUE_WORDS:
        if cue in full_text:
            return True

    return False


async def extract_and_store_memories(
    spec: AgentSpec,
    user_messages: Sequence[str],
    final_output: str,
    execution_id: str,
    store: MemoryStore,
    llm_complete_fn: Any = None,
) -> list[str]:
    """Extract durable memories from user messages and store them after safety validation."""
    if not should_trigger_extraction(spec, user_messages):
        return []

    # Get existing active items for deduplication
    existing_items = await store.related(spec.id, " ".join(user_messages)[:500], limit=20)

    # If LLM complete function is supplied, invoke extraction call
    candidates: list[MemoryCandidate] = []
    if llm_complete_fn:
        prompt = (
            "Extract 0 to 3 durable user facts, preferences, or decisions from the user's messages.\n"
            "Return strictly valid JSON with format:\n"
            "{\"memories\": [{\"text\": \"User works on Orion project\", \"kind\": \"fact\", \"evidence\": \"I work on Orion\"}]}\n"
            f"User messages:\n" + "\n".join(user_messages)
        )
        try:
            turn = await llm_complete_fn([{"role": "user", "content": prompt}])
            if turn.text:
                data = json.loads(turn.text)
                for item in data.get("memories", []):
                    candidates.append(
                        MemoryCandidate(
                            text=item.get("text", ""),
                            kind=item.get("kind", "fact"),
                            source_type="user_stated",
                            source_execution_id=execution_id,
                            evidence=item.get("evidence", ""),
                            supersedes=item.get("supersedes", []),
                        )
                    )
        except Exception as e:
            logger.warning(f"Memory extraction call failed: {e}")
            return []

    # Validate candidates against safety filters
    valid_candidates = []
    for cand in candidates:
        if validate_and_filter_candidate(cand, user_messages, existing_items):
            valid_candidates.append(cand)

    if not valid_candidates:
        return []

    added_items = await store.add(spec.id, valid_candidates)
    return [item.id for item in added_items]
