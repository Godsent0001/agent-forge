"""SQLite-backed MemoryStore and LessonStore implementations for the v2 Runner."""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session, sessionmaker

from app import models
from app.contracts.memory import Lesson, MemoryCandidate, MemoryHit, MemoryItem
from app.db import SessionLocal


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _memory_item(row: models.MemoryEntry) -> MemoryItem:
    return MemoryItem(
        id=row.id,
        agent_id=row.agent_id,
        text=row.content,
        kind=row.kind if row.kind in {"fact", "preference", "decision"} else "fact",
        source_type=row.source_type if row.source_type in {"user_stated", "user_edited", "inferred"} else "user_stated",
        source_execution_id=row.source_execution_id,
        evidence=row.evidence or "",
        expires_at=_utc(row.expires_at),
        embedding=row.embedding,
        embedding_model=row.embedding_model,
        created_at=_utc(row.created_at) or datetime.now(timezone.utc),
        last_used_at=_utc(row.last_used_at),
        use_count=row.use_count or 0,
        pinned=bool(row.pinned),
        status=row.status if row.status in {"active", "superseded", "archived"} else "active",
    )


def _lesson(row: models.LessonEntry) -> Lesson:
    return Lesson(
        id=row.id,
        agent_id=row.agent_id,
        text=row.text,
        evidence_execution_id=row.evidence_execution_id,
        status=row.status if row.status in {"active", "archived"} else "active",
        score=float(row.score or 0.0),
        created_at=_utc(row.created_at) or datetime.now(timezone.utc),
    )


def _not_expired(row: models.MemoryEntry, now: datetime) -> bool:
    expiry = _utc(row.expires_at)
    return row.status == "active" and (expiry is None or expiry > now)


def _keyword_score(text: str, query: str) -> float:
    query_terms = {term.lower().strip(".,!?;:'\"()[]{}") for term in query.split() if term.strip()}
    query_terms.discard("")
    if not query_terms:
        return 0.0
    item_terms = {term.lower().strip(".,!?;:'\"()[]{}") for term in text.split() if term.strip()}
    return min(1.0, len(query_terms & item_terms) / len(query_terms))


class SqlMemoryStore:
    """Persist semantic memory using the same contract as the in-memory test store."""

    def __init__(self, session_factory: Callable[[], Session] | sessionmaker = SessionLocal):
        self._session_factory = session_factory

    async def pinned(self, agent_id: str) -> list[MemoryItem]:
        now = datetime.now(timezone.utc)
        with self._session_factory() as db:
            rows = db.query(models.MemoryEntry).filter(
                models.MemoryEntry.agent_id == agent_id,
                models.MemoryEntry.pinned.is_(True),
                models.MemoryEntry.status == "active",
            ).order_by(models.MemoryEntry.created_at.desc()).all()
            return [_memory_item(row) for row in rows if _not_expired(row, now)]

    async def candidates(
        self,
        agent_id: str,
        query: str,
        limit: int,
        *,
        query_embedding: list[float] | None = None,
        embedding_model: str | None = None,
    ) -> list[MemoryHit]:
        if limit <= 0:
            return []
        now = datetime.now(timezone.utc)
        with self._session_factory() as db:
            rows = db.query(models.MemoryEntry).filter(
                models.MemoryEntry.agent_id == agent_id,
                models.MemoryEntry.status == "active",
            ).order_by(models.MemoryEntry.created_at.desc()).all()
            hits = []
            for row in rows:
                if not _not_expired(row, now):
                    continue
                item = _memory_item(row)
                keyword = _keyword_score(item.text, query)
                vector = 0.0
                if query_embedding and item.embedding and item.embedding_model == embedding_model:
                    pairs = list(zip(query_embedding, item.embedding))
                    dot = sum(a * b for a, b in pairs)
                    left_norm = math.sqrt(sum(a * a for a, _ in pairs))
                    right_norm = math.sqrt(sum(b * b for _, b in pairs))
                    if left_norm and right_norm:
                        vector = max(0.0, min(1.0, dot / (left_norm * right_norm)))
                if keyword > 0 or vector > 0 or item.pinned:
                    hits.append(MemoryHit(item=item, keyword_score=keyword, vector_score=vector))
            hits.sort(key=lambda hit: (hit.item.pinned, hit.keyword_score * 0.6 + hit.vector_score * 0.4), reverse=True)
            return hits[:limit]

    async def related(self, agent_id: str, text: str, limit: int) -> list[MemoryItem]:
        with self._session_factory() as db:
            rows = db.query(models.MemoryEntry).filter(
                models.MemoryEntry.agent_id == agent_id,
                models.MemoryEntry.status == "active",
            ).order_by(models.MemoryEntry.created_at.desc()).all()
            matched = [row for row in rows if _keyword_score(row.content, text) > 0]
            return [_memory_item(row) for row in matched[:max(0, limit)]]

    async def add(self, agent_id: str, items: list[MemoryCandidate]) -> list[MemoryItem]:
        if not items:
            return []
        now = datetime.now(timezone.utc)
        created: list[MemoryItem] = []
        with self._session_factory() as db:
            if db.get(models.Agent, agent_id) is None:
                return []
            for candidate in items:
                for superseded_id in candidate.supersedes:
                    row = db.query(models.MemoryEntry).filter_by(id=superseded_id, agent_id=agent_id).first()
                    if row is not None and row.status == "active":
                        row.status = "superseded"
                row = models.MemoryEntry(
                    id=str(uuid.uuid4()),
                    agent_id=agent_id,
                    content=candidate.text.strip()[:200],
                    kind=candidate.kind,
                    source_type=candidate.source_type,
                    evidence=candidate.evidence,
                    source_execution_id=candidate.source_execution_id,
                    expires_at=candidate.expires_at,
                    embedding=candidate.embedding,
                    embedding_model=candidate.embedding_model,
                    status="active",
                    created_at=now,
                )
                db.add(row)
                db.flush()
                created.append(_memory_item(row))
            db.commit()
            return created

    async def touch(self, ids: list[str], execution_id: str) -> None:
        if not ids:
            return
        now = datetime.now(timezone.utc)
        with self._session_factory() as db:
            rows = db.query(models.MemoryEntry).filter(models.MemoryEntry.id.in_(ids)).all()
            for row in rows:
                row.last_used_at = now
                row.use_count = (row.use_count or 0) + 1
            db.commit()

    async def missing_embeddings(self, agent_id: str, model: str, limit: int) -> list[MemoryItem]:
        with self._session_factory() as db:
            rows = db.query(models.MemoryEntry).filter(
                models.MemoryEntry.agent_id == agent_id,
                models.MemoryEntry.status == "active",
            ).order_by(models.MemoryEntry.created_at.desc()).all()
            return [
                _memory_item(row)
                for row in rows
                if row.embedding is None or row.embedding_model != model
            ][:max(0, limit)]

    async def set_embeddings(self, pairs: list[tuple[str, list[float], str]]) -> None:
        if not pairs:
            return
        with self._session_factory() as db:
            for memory_id, vector, model_name in pairs:
                row = db.get(models.MemoryEntry, memory_id)
                if row is not None:
                    row.embedding = vector
                    row.embedding_model = model_name
            db.commit()


class SqlLessonStore:
    """Persistent lesson store implementing the Runner's LessonStore protocol."""

    def __init__(self, session_factory: Callable[[], Session] | sessionmaker = SessionLocal):
        self._session_factory = session_factory

    async def active(self, agent_id: str, limit: int) -> list[Lesson]:
        with self._session_factory() as db:
            rows = db.query(models.LessonEntry).filter(
                models.LessonEntry.agent_id == agent_id,
                models.LessonEntry.status == "active",
            ).order_by(models.LessonEntry.score.desc(), models.LessonEntry.created_at.desc()).limit(max(0, limit)).all()
            return [_lesson(row) for row in rows]

    async def add(self, lesson: Lesson) -> None:
        with self._session_factory() as db:
            existing = db.get(models.LessonEntry, lesson.id)
            if existing is not None:
                return
            db.add(models.LessonEntry(
                id=lesson.id,
                agent_id=lesson.agent_id,
                text=lesson.text[:300],
                evidence_execution_id=lesson.evidence_execution_id,
                status=lesson.status,
                score=lesson.score,
                created_at=lesson.created_at,
            ))
            db.commit()
