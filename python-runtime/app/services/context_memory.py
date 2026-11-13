"""Server-owned conversation context for durable project workstreams.

A workstream (task) can span several conversations. Its message stream is the
user/assistant messages of every conversation linked to it, in time order. The
workstream stores one rolling summary plus a cursor marking the last message the
summary covers; everything after the cursor is sent to the model verbatim, up to
a token budget derived from the model's context window (see core.memory.compaction).
"""
from __future__ import annotations

import asyncio
import copy
from typing import Any

from sqlalchemy.orm import Session

from app import models
from app.core.memory.compaction import (
    SummarizeFn,
    merge_history,
    split_for_budget,
    summarize_evicted,
)

SUMMARY_KEY = "context_summary"
# Upper bound on what the request path loads before the runner compacts it.
_LOAD_MAX_CHARS = 200_000


def _linked_conversation_ids(db: Session, task: models.TaskState, conversation_id: str) -> set[str]:
    ids = {task.conversation_id, conversation_id}
    events = db.query(models.TaskStateEvent).filter(models.TaskStateEvent.task_state_id == task.id).all()
    for event in events:
        payload = event.payload if isinstance(event.payload, dict) else {}
        for key in ("conversation_id", "previous_conversation_id", "resumed_in_conversation_id"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                ids.add(value)
    return ids


def _stream(db: Session, conversation_ids: set[str], current_task: str) -> list[models.ConversationMessage]:
    messages = (
        db.query(models.ConversationMessage)
        .filter(
            models.ConversationMessage.conversation_id.in_(sorted(conversation_ids)),
            models.ConversationMessage.role.in_(["user", "assistant"]),
        )
        .order_by(models.ConversationMessage.created_at, models.ConversationMessage.id)
        .all()
    )
    # The message being answered is sent separately as the current task.
    if messages and messages[-1].role == "user" and (messages[-1].content or "").strip() == current_task.strip():
        messages = messages[:-1]
    return messages


def _legacy_summary(stored: dict[str, Any]) -> str:
    """Carry over the keyword-extract summary written by the first implementation."""
    lines: list[str] = []
    for label, key in (("Goals, decisions and constraints:", "pinned"), ("Progress:", "progress")):
        values = [value for value in stored.get(key) or [] if isinstance(value, str) and value.strip()]
        if values:
            lines.extend([label, *values])
    return "\n".join(lines)


def _resume_point(stored: Any, stream: list[models.ConversationMessage]) -> tuple[str, int]:
    """Return (summary, index of the first message the summary does not cover).

    The cursor is trusted only if the stream before it is unchanged. If a covered
    message was edited away or deleted, the summary is discarded and rebuilt.
    """
    if not isinstance(stored, dict):
        return "", 0
    if "cursors" in stored:  # format written before the rolling summary existed
        covered = {
            cursor.get("last_id") for cursor in (stored.get("cursors") or {}).values()
            if isinstance(cursor, dict)
        }
        last = max((index for index, message in enumerate(stream) if message.id in covered), default=-1)
        return _legacy_summary(stored), last + 1
    last_id = stored.get("last_id")
    count = stored.get("count")
    summary = stored.get("summary")
    if not isinstance(last_id, str) or not isinstance(count, int) or not isinstance(summary, str):
        return "", 0
    if 0 < count <= len(stream) and stream[count - 1].id == last_id:
        return summary, count
    return "", 0


def _bounded_tail(messages: list[models.ConversationMessage], max_chars: int) -> list[models.ConversationMessage]:
    used = 0
    start = len(messages)
    for index in range(len(messages) - 1, -1, -1):
        used += len(messages[index].content or "")
        if used > max_chars and start < len(messages):
            break
        start = index
    return messages[start:]


def build_conversation_context(db: Session, task_state_id: str | None, conversation_id: str, current_task: str):
    """Read-only view for the request path: (history, summary, transcript_available).

    History is every message the stored summary does not cover. It is not trimmed
    to the model here; the runner compacts it against the model's context window.
    """
    task = db.get(models.TaskState, task_state_id) if task_state_id else None
    ids = _linked_conversation_ids(db, task, conversation_id) if task is not None else {conversation_id}
    stream = _stream(db, ids, current_task)
    summary, start = _resume_point((task.state_json or {}).get(SUMMARY_KEY) if task is not None else None, stream)
    pending = _bounded_tail(stream[start:], _LOAD_MAX_CHARS)
    return merge_history(pending), summary, bool(stream)


def _load(session_factory, task_state_id: str | None, conversation_id: str, current_task: str):
    with session_factory() as db:
        task = db.get(models.TaskState, task_state_id) if task_state_id else None
        ids = _linked_conversation_ids(db, task, conversation_id) if task is not None else {conversation_id}
        stream = _stream(db, ids, current_task)
        summary, start = _resume_point(
            (task.state_json or {}).get(SUMMARY_KEY) if task is not None else None, stream
        )
        rows = [{"id": m.id, "role": m.role, "content": m.content or ""} for m in stream]
        return task is not None, rows, summary, start


def _save(session_factory, task_state_id: str, summary: str, last_id: str, count: int) -> None:
    with session_factory() as db:
        task = db.get(models.TaskState, task_state_id)
        if task is None:
            return
        # Re-read inside this transaction: other writers update the same JSON document.
        state = copy.deepcopy(dict(task.state_json or {}))
        state[SUMMARY_KEY] = {"summary": summary, "last_id": last_id, "count": count}
        task.state_json = state
        db.commit()


async def compact_conversation_context(
    task_state_id: str | None,
    conversation_id: str,
    current_task: str,
    *,
    budget_chars: int,
    summarize_fn: SummarizeFn | None = None,
    session_factory: Any = None,
) -> tuple[list[dict[str, str]], str] | None:
    """Return (history, summary) fitted to the budget, folding overflow into the summary.

    Returns None when the conversation has no stored transcript, so the caller
    can fall back to client-supplied history.
    """
    if session_factory is None:
        from app.db import SessionLocal
        session_factory = SessionLocal
    has_task, rows, summary, start = await asyncio.to_thread(
        _load, session_factory, task_state_id, conversation_id, current_task
    )
    if not rows:
        return None
    evicted, kept = split_for_budget(rows[start:], budget_chars)
    if evicted:
        if has_task:
            summary, _ = await summarize_evicted(summary, evicted, summarize_fn)
            await asyncio.to_thread(
                _save, session_factory, task_state_id, summary, evicted[-1]["id"], start + len(evicted)
            )
        # Without a workstream there is nowhere durable to keep a summary; the
        # evicted messages stay retrievable through transcript search.
    return merge_history(kept), summary
