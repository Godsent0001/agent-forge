"""C-6: memory, run history, intents, insights, lessons. Pure data and protocols
(see docs/CONTRACTS.md and docs/MEMORY.md)."""
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel

# ---- limits (MEMORY.md) -------------------------------------------------
MAX_MEMORY_TEXT_CHARS = 200
MAX_INTENT_TEXT_CHARS = 300
MAX_INSIGHT_TEXT_CHARS = 300

# ---- semantic memory ----------------------------------------------------
MemoryKind = Literal["fact", "preference", "decision"]
# user_stated: said by the user. user_edited: typed in the UI.
# inferred: found by a dream and ACCEPTED by the user.
MemorySource = Literal["user_stated", "user_edited", "inferred"]
MemoryStatus = Literal["active", "superseded", "archived"]


class MemoryCandidate(BaseModel):
    text: str                                # one self-contained statement, max 200 chars
    kind: MemoryKind = "fact"
    source_type: MemorySource = "user_stated"
    source_execution_id: str | None = None
    evidence: str = ""                       # verbatim user quote (checked by the core)
    supersedes: list[str] = []               # ids of existing items this one replaces
    expires_at: datetime | None = None
    embedding: list[float] | None = None     # never sent to the UI
    embedding_model: str | None = None


class MemoryItem(MemoryCandidate):
    id: str
    agent_id: str
    created_at: datetime
    last_used_at: datetime | None = None
    use_count: int = 0
    pinned: bool = False
    status: MemoryStatus = "active"


class MemoryHit(BaseModel):
    item: MemoryItem
    keyword_score: float = 0.0               # 0..1 (FTS5 bm25, normalized)
    vector_score: float = 0.0                # 0..1 cosine; 0 if no usable embedding


class MemoryStore(Protocol):
    # Reads return only active, non-expired items.
    async def pinned(self, agent_id: str) -> list[MemoryItem]: ...
    async def candidates(self, agent_id: str, query: str, limit: int, *,
                         query_embedding: list[float] | None = None,
                         embedding_model: str | None = None) -> list[MemoryHit]: ...
    async def related(self, agent_id: str, text: str, limit: int) -> list[MemoryItem]: ...
    async def add(self, agent_id: str, items: list[MemoryCandidate]) -> list[MemoryItem]: ...
    # add() also marks `supersedes` targets "superseded", in one transaction.
    async def touch(self, ids: list[str], execution_id: str) -> None: ...
    async def missing_embeddings(self, agent_id: str, model: str, limit: int) -> list[MemoryItem]: ...
    async def set_embeddings(self, pairs: list[tuple[str, list[float], str]]) -> None: ...  # (id, vector, model)


# ---- episodic memory (read-only view over past runs) --------------------
class RunDigest(BaseModel):
    execution_id: str
    agent_id: str
    started_at: datetime
    task_preview: str
    status: str
    final_output_preview: str = ""
    errors: list[str] = []                   # up to 3, each cut to 200 chars (tool/LLM error text: UNTRUSTED)
    feedback: Literal["up", "down"] | None = None


class RunHistory(Protocol):
    async def search(self, agent_id: str, query: str, limit: int) -> list[RunDigest]: ...
    async def recent(self, agent_id: str, *, since: datetime, limit: int,
                     only_problems: bool = False) -> list[RunDigest]: ...


# ---- standing intents (reminders) ---------------------------------------
IntentTrigger = Literal["next_run", "at_time"]
IntentMode = Literal["remind", "auto_run"]
IntentStatus = Literal["active", "fired", "cancelled", "expired"]


class Intent(BaseModel):
    id: str
    agent_id: str
    text: str                                # max 300 chars: what to remind or do
    trigger: IntentTrigger
    due_at: datetime | None = None           # UTC; required for at_time
    repeat: Literal["none", "daily", "weekly"] = "none"
    mode: IntentMode = "remind"              # auto_run can ONLY be set from the UI
    status: IntentStatus = "active"
    evidence: str = ""                       # verbatim user quote
    source_execution_id: str | None = None
    created_at: datetime
    last_fired_at: datetime | None = None


class IntentStore(Protocol):
    async def create(self, intent: Intent) -> Intent: ...
    async def due_for_run(self, agent_id: str, now: datetime) -> list[Intent]: ...  # active and (next_run, or at_time <= now)
    async def mark_fired(self, ids: list[str], now: datetime) -> None: ...          # applies `repeat`, else status "fired"
    async def cancel(self, intent_id: str) -> None: ...
    async def list(self, agent_id: str, status: IntentStatus | None = None) -> list[Intent]: ...


# ---- insights ("dreams"): suggestions only, until the user accepts ------
InsightStatus = Literal["pending", "accepted", "dismissed"]


class Insight(BaseModel):
    id: str
    agent_id: str
    text: str                                # max 300 chars
    kind: Literal["pattern", "suggestion"]
    evidence_execution_ids: list[str]
    status: InsightStatus = "pending"
    maintenance_run_id: str | None = None
    created_at: datetime


class InsightStore(Protocol):
    async def add(self, items: list[Insight]) -> None: ...
    async def list(self, agent_id: str, status: InsightStatus | None = None) -> list[Insight]: ...
    async def resolve(self, insight_id: str, status: InsightStatus) -> None: ...
    # Accepting also writes a MemoryItem (source_type="inferred") in the same transaction (platform).


# ---- lessons (draft: A-07 may extend this through a `contract` PR) ------
class Lesson(BaseModel):
    id: str
    agent_id: str
    text: str
    evidence_execution_id: str | None = None
    status: Literal["active", "archived"] = "active"
    score: float = 0.0
    created_at: datetime


class LessonStore(Protocol):
    async def active(self, agent_id: str, limit: int) -> list[Lesson]: ...
    async def add(self, lesson: Lesson) -> None: ...
