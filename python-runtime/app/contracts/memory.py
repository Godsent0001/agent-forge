from datetime import datetime
from typing import Literal, Protocol
from pydantic import BaseModel


class MemoryCandidate(BaseModel):
    text: str
    kind: Literal["fact", "preference", "decision"] = "fact"
    source_execution_id: str | None = None


class MemoryItem(MemoryCandidate):
    id: str
    created_at: datetime
    pinned: bool = False


class MemoryStore(Protocol):
    async def recall(self, agent_id: str, query: str, budget_tokens: int) -> list[MemoryItem]: ...
    async def add(self, agent_id: str, items: list[MemoryCandidate]) -> None: ...
    async def summary(self, agent_id: str) -> str: ...
    async def set_summary(self, agent_id: str, text: str) -> None: ...


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
