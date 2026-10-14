"""Idle background synthesis (dreams) generating suggestions/insights."""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.contracts.memory import Insight, InsightStore, MemoryStore, RunHistory

logger = logging.getLogger(__name__)


async def run_dream_synthesis(
    agent_id: str,
    run_history: RunHistory,
    memory_store: MemoryStore,
    insight_store: InsightStore,
    llm_complete_fn: Any,
) -> list[Insight]:
    """Perform idle background synthesis generating insights."""
    now = datetime.now(timezone.utc)

    # 1. Fetch recent digests and memory titles
    digests = await run_history.recent(agent_id=agent_id, since=now, limit=10, only_problems=False)
    pinned_memories = await memory_store.pinned(agent_id)

    if not digests:
        return []

    valid_exec_ids = {d.execution_id for d in digests}
    digest_summaries = [f"- Exec {d.execution_id}: Task=\"{d.task_preview}\" Output=\"{d.final_output_preview}\" Status={d.status}" for d in digests]
    memory_summaries = [f"- {m.text}" for m in pinned_memories]

    prompt = (
        "Analyze recent agent activity and active memories to find actionable insights or suggestions.\n"
        "Output strictly valid JSON with format:\n"
        "{\"insights\": [{\"text\": \"User frequently asks for weather summaries\", \"kind\": \"pattern\", \"evidence_execution_ids\": [\"exec_1\", \"exec_2\"]}]}\n"
        "Rules:\n"
        "- Max 3 insights\n"
        "- Each insight must cite existing execution_ids from the list below\n\n"
        "Recent executions:\n" + "\n".join(digest_summaries) + "\n\n"
        "Active memories:\n" + "\n".join(memory_summaries)
    )

    try:
        turn = await llm_complete_fn([{"role": "user", "content": prompt}])
        if not turn.text:
            return []

        data = json.loads(turn.text)
        created_insights: list[Insight] = []

        for item in data.get("insights", []):
            text = item.get("text", "").strip()
            kind = item.get("kind", "pattern")
            cited_ids = item.get("evidence_execution_ids", [])

            if not text or len(text) > 300:
                continue

            # Verify cited IDs exist
            valid_cites = [cid for cid in cited_ids if cid in valid_exec_ids]
            if not valid_cites:
                continue

            insight = Insight(
                id=str(uuid.uuid4()),
                agent_id=agent_id,
                text=text,
                kind=kind,
                evidence_execution_ids=valid_cites,
                status="pending",
                created_at=now,
            )
            created_insights.append(insight)

        if created_insights and insight_store:
            await insight_store.add(created_insights)

        return created_insights

    except Exception as e:
        logger.warning(f"Dream synthesis failed: {e}")
        return []
