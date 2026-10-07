"""In-memory implementations of MemoryStore, IntentStore, RunHistory, and InsightStore for testing."""
import uuid
from datetime import datetime, timezone
from typing import Literal

from app.contracts.memory import (
    Insight,
    InsightStatus,
    Intent,
    IntentStatus,
    MemoryCandidate,
    MemoryHit,
    MemoryItem,
    RunDigest,
)


class InMemoryStore:
    """In-memory implementation of MemoryStore protocol."""

    def __init__(self):
        self.items: dict[str, MemoryItem] = {}

    async def pinned(self, agent_id: str) -> list[MemoryItem]:
        return [
            item for item in self.items.values()
            if item.agent_id == agent_id and item.pinned and item.status == "active"
        ]

    async def candidates(
        self,
        agent_id: str,
        query: str,
        limit: int,
        *,
        query_embedding: list[float] | None = None,
        embedding_model: str | None = None,
    ) -> list[MemoryHit]:
        active_items = [
            item for item in self.items.values()
            if item.agent_id == agent_id and item.status == "active"
        ]
        hits: list[MemoryHit] = []
        query_terms = set(query.lower().split())

        for item in active_items:
            item_terms = set(item.text.lower().split())
            overlap = len(query_terms.intersection(item_terms))
            kw_score = min(1.0, overlap / max(1, len(query_terms)))

            vec_score = 0.0
            if query_embedding and item.embedding and item.embedding_model == embedding_model:
                dot = sum(a * b for a, b in zip(query_embedding, item.embedding))
                vec_score = max(0.0, dot)

            if kw_score > 0 or vec_score > 0 or item.pinned:
                hits.append(MemoryHit(item=item, keyword_score=kw_score, vector_score=vec_score))

        hits.sort(key=lambda h: (h.item.pinned, h.keyword_score * 0.6 + h.vector_score * 0.4), reverse=True)
        return hits[:limit]

    async def related(self, agent_id: str, text: str, limit: int) -> list[MemoryItem]:
        query_terms = set(text.lower().split())
        matched = []
        for item in self.items.values():
            if item.agent_id == agent_id and item.status == "active":
                item_terms = set(item.text.lower().split())
                if query_terms.intersection(item_terms):
                    matched.append(item)
        return matched[:limit]

    async def add(self, agent_id: str, items: list[MemoryCandidate]) -> list[MemoryItem]:
        created: list[MemoryItem] = []
        now = datetime.now(timezone.utc)

        for candidate in items:
            # Supersede marked items
            for sup_id in candidate.supersedes:
                if sup_id in self.items:
                    self.items[sup_id].status = "superseded"

            item_id = str(uuid.uuid4())
            item = MemoryItem(
                id=item_id,
                agent_id=agent_id,
                text=candidate.text,
                kind=candidate.kind,
                source_type=candidate.source_type,
                source_execution_id=candidate.source_execution_id,
                evidence=candidate.evidence,
                created_at=now,
                status="active",
                expires_at=candidate.expires_at,
                embedding=candidate.embedding,
                embedding_model=candidate.embedding_model,
            )
            self.items[item_id] = item
            created.append(item)

        return created

    async def touch(self, ids: list[str], execution_id: str) -> None:
        now = datetime.now(timezone.utc)
        for item_id in ids:
            if item_id in self.items:
                self.items[item_id].last_used_at = now
                self.items[item_id].use_count += 1

    async def missing_embeddings(self, agent_id: str, model: str, limit: int) -> list[MemoryItem]:
        missing = [
            item for item in self.items.values()
            if item.agent_id == agent_id and (not item.embedding or item.embedding_model != model)
        ]
        return missing[:limit]

    async def set_embeddings(self, pairs: list[tuple[str, list[float], str]]) -> None:
        for item_id, vector, model_name in pairs:
            if item_id in self.items:
                self.items[item_id].embedding = vector
                self.items[item_id].embedding_model = model_name


class InMemoryIntentStore:
    """In-memory implementation of IntentStore protocol."""

    def __init__(self):
        self.intents: dict[str, Intent] = {}

    async def create(self, intent: Intent) -> Intent:
        self.intents[intent.id] = intent
        return intent

    async def due_for_run(self, agent_id: str, now: datetime) -> list[Intent]:
        due: list[Intent] = []
        for i in self.intents.values():
            if i.agent_id == agent_id and i.status == "active":
                if i.trigger == "next_run":
                    due.append(i)
                elif i.trigger == "at_time" and i.due_at and i.due_at <= now:
                    due.append(i)
        return due

    async def mark_fired(self, ids: list[str], now: datetime) -> None:
        for item_id in ids:
            if item_id in self.intents:
                intent = self.intents[item_id]
                intent.last_fired_at = now
                if intent.repeat == "none":
                    intent.status = "fired"

    async def cancel(self, intent_id: str) -> None:
        if intent_id in self.intents:
            self.intents[intent_id].status = "cancelled"

    async def list(self, agent_id: str, status: IntentStatus | None = None) -> list[Intent]:
        res = [i for i in self.intents.values() if i.agent_id == agent_id]
        if status:
            res = [i for i in res if i.status == status]
        return res


class InMemoryRunHistory:
    """In-memory implementation of RunHistory protocol."""

    def __init__(self):
        self.digests: list[RunDigest] = []

    async def search(self, agent_id: str, query: str, limit: int) -> list[RunDigest]:
        q = query.lower()
        res = [
            d for d in self.digests
            if d.agent_id == agent_id and (q in d.task_preview.lower() or q in d.final_output_preview.lower())
        ]
        return res[:limit]

    async def recent(
        self, agent_id: str, *, since: datetime, limit: int, only_problems: bool = False
    ) -> list[RunDigest]:
        res = [d for d in self.digests if d.agent_id == agent_id and d.started_at >= since]
        if only_problems:
            res = [d for d in res if d.status in ("error", "budget_exceeded", "cancelled") or d.errors or d.feedback == "down"]
        res.sort(key=lambda x: x.started_at, reverse=True)
        return res[:limit]


class InMemoryInsightStore:
    """In-memory implementation of InsightStore protocol."""

    def __init__(self):
        self.insights: dict[str, Insight] = {}

    async def add(self, items: list[Insight]) -> None:
        for item in items:
            self.insights[item.id] = item

    async def list(self, agent_id: str, status: InsightStatus | None = None) -> list[Insight]:
        res = [i for i in self.insights.values() if i.agent_id == agent_id]
        if status:
            res = [i for i in res if i.status == status]
        return res

    async def resolve(self, insight_id: str, status: InsightStatus) -> None:
        if insight_id in self.insights:
            self.insights[insight_id].status = status
