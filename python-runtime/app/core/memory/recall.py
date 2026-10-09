"""Memory recall logic and scoring formula per MEMORY.md 5.1."""
import math
from datetime import datetime, timezone
from app.contracts.memory import MemoryHit, MemoryItem, MemoryStore


def score_memory(
    hit: MemoryHit,
    now: datetime,
) -> float:
    """Compute composite score for a memory hit."""
    item = hit.item
    age_days = (now - item.created_at).total_seconds() / 86400.0
    half_life = 90.0 if item.kind == "preference" else 30.0
    recency = math.exp(-age_days / half_life)

    usage = min(item.use_count, 10) / 10.0

    if hit.vector_score > 0:
        score = 0.45 * hit.vector_score + 0.25 * hit.keyword_score + 0.20 * recency + 0.10 * usage
    else:
        score = 0.60 * hit.keyword_score + 0.25 * recency + 0.15 * usage

    return score


async def recall_memories(
    store: MemoryStore,
    agent_id: str,
    query: str,
    recall_budget_tokens: int = 800,
    query_embedding: list[float] | None = None,
    embedding_model: str | None = None,
    now: datetime | None = None,
) -> tuple[list[MemoryItem], str]:
    """Recall pinned and top candidate memories within token budget."""
    now = now or datetime.now(timezone.utc)

    pinned_items = await store.pinned(agent_id)
    candidates = await store.candidates(
        agent_id=agent_id,
        query=query,
        limit=30,
        query_embedding=query_embedding,
        embedding_model=embedding_model,
    )

    # Filter out pinned items from candidates to avoid duplicates
    pinned_ids = {p.id for p in pinned_items}
    non_pinned_hits = [c for c in candidates if c.item.id not in pinned_ids]

    scored_hits = [(score_memory(hit, now), hit) for hit in non_pinned_hits]
    scored_hits.sort(key=lambda pair: pair[0], reverse=True)

    selected: list[MemoryItem] = []
    used_tokens = 0
    max_tokens = recall_budget_tokens

    # 1. Include pinned items first
    for item in pinned_items:
        item_tokens = len(item.text) // 4 + 1
        if used_tokens + item_tokens > max_tokens:
            continue
        selected.append(item)
        used_tokens += item_tokens

    # 2. Include top candidates until token limit or 12 items max
    for score, hit in scored_hits:
        if len(selected) >= 12:
            break
        item = hit.item
        item_tokens = len(item.text) // 4 + 1
        if used_tokens + item_tokens > max_tokens:
            break
        selected.append(item)
        used_tokens += item_tokens

    # Format memory prompt block
    lines = []
    for item in selected:
        inferred_tag = " (inferred)" if item.source_type == "inferred" else ""
        lines.append(f"- [{item.kind}] {item.text}{inferred_tag}")

    block = "\n".join(lines)
    return selected, block
