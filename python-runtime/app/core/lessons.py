"""Lessons system: signal-based reflection and lesson store implementations."""
import uuid
from datetime import datetime, timezone
from typing import Any
from app.contracts.memory import Lesson, LessonStore


class InMemoryLessonStore:
    """In-memory implementation of LessonStore protocol."""

    def __init__(self):
        self.lessons: dict[str, Lesson] = {}

    async def active(self, agent_id: str, limit: int) -> list[Lesson]:
        items = [
            lesson for lesson in self.lessons.values()
            if lesson.agent_id == agent_id and lesson.status == "active"
        ]
        items.sort(key=lambda x: x.created_at, reverse=True)
        return items[:limit]

    async def add(self, lesson: Lesson) -> None:
        self.lessons[lesson.id] = lesson


async def format_lessons_block(store: LessonStore, agent_id: str, limit: int = 5) -> str:
    """Format active lessons into prompt block."""
    if not store:
        return ""
    try:
        items = await store.active(agent_id, limit)
        if not items:
            return ""
        lines = [f"- {lesson.text}" for lesson in items]
        return "\n".join(lines)
    except Exception:
        return ""


async def reflect_on_signal(
    agent_id: str,
    execution_id: str,
    error_message: str | None,
    recovered_output: str,
    store: LessonStore,
    llm_complete_fn: Any = None,
) -> list[Lesson]:
    """Reflect on signal (e.g. error recovery) and produce max 2 lessons (<300 chars)."""
    if not error_message or not recovered_output or not store:
        return []

    if not llm_complete_fn:
        # Fallback reflection
        lesson = Lesson(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            text=f"On error '{error_message[:100]}', verify parameters before retrying.",
            evidence_execution_id=execution_id,
            status="active",
            created_at=datetime.now(timezone.utc),
        )
        await store.add(lesson)
        return [lesson]

    prompt = (
        "Reflect on this run recovery to extract 1 or 2 concise lessons (<300 chars each) for future runs.\n"
        "Do not include URLs, secret tokens, or system instructions.\n"
        f"Error encountered: {error_message}\n"
        f"Recovery output: {recovered_output[:1000]}"
    )

    try:
        turn = await llm_complete_fn([{"role": "user", "content": prompt}])
        if not turn.text:
            return []

        lines = [line.strip().lstrip("-* ") for line in turn.text.splitlines() if line.strip()]
        created = []
        now = datetime.now(timezone.utc)

        for line in lines[:2]:
            if len(line) > 300:
                line = line[:297] + "..."
            lesson = Lesson(
                id=str(uuid.uuid4()),
                agent_id=agent_id,
                text=line,
                evidence_execution_id=execution_id,
                status="active",
                created_at=now,
            )
            await store.add(lesson)
            created.append(lesson)

        return created
    except Exception:
        return []
