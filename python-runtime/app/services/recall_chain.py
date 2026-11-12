"""Small, ID-based recall index over the existing append-only task history."""
from __future__ import annotations

from typing import Any

from app import models
from sqlalchemy.orm import Session


_CONVERSATION_KEYS = ("conversation_id", "previous_conversation_id", "resumed_in_conversation_id")
_MESSAGE_KEYS = ("message_id", "source_message_id", "evidence_message_id")


def _add(values: list[str], value: Any) -> None:
    if isinstance(value, str) and value and value not in values:
        values.append(value)


def build_recall_chain(db: Session, task_state_id: str, *, limit: int = 40) -> dict[str, Any]:
    """Return stable IDs linking a task to its source conversations and evidence."""
    task = db.get(models.TaskState, task_state_id)
    if task is None:
        return {"task_id": task_state_id, "conversations": [], "executions": [], "messages": [], "artifacts": [], "events": []}
    result: dict[str, Any] = {"task_id": task.id, "conversations": [], "executions": [], "messages": [], "artifacts": [], "events": []}
    _add(result["conversations"], task.conversation_id)
    events = (db.query(models.TaskStateEvent)
        .filter(models.TaskStateEvent.task_state_id == task.id)
        .order_by(models.TaskStateEvent.created_at, models.TaskStateEvent.id).all())
    for event in events:
        _add(result["events"], event.id)
        _add(result["executions"], event.source_execution_id)
        payload = event.payload if isinstance(event.payload, dict) else {}
        for key in _CONVERSATION_KEYS:
            _add(result["conversations"], payload.get(key))
        for key in _MESSAGE_KEYS:
            _add(result["messages"], payload.get(key))
        _add(result["executions"], payload.get("execution_id"))
        for key in ("message_ids", "evidence_message_ids"):
            values = payload.get(key)
            if isinstance(values, list):
                for value in values:
                    _add(result["messages"], value)
        for key in ("artifact_id", "file_id"):
            _add(result["artifacts"], payload.get(key))
        for key in ("artifact_ids", "file_ids"):
            values = payload.get(key)
            if isinstance(values, list):
                for value in values:
                    _add(result["artifacts"], value)
    for key in ("conversations", "executions", "messages", "artifacts", "events"):
        result[key] = result[key][-max(1, limit):]
    return result


def render_recall_chain(chain: dict[str, Any]) -> str:
    """Render stable identifiers only; source records remain canonical."""
    lines = [f"Task ID: {chain.get('task_id', '')}"]
    for key, label in (("conversations", "Conversation IDs"), ("executions", "Execution IDs"),
                       ("messages", "Source message IDs"), ("artifacts", "Artifact IDs")):
        values = chain.get(key)
        if isinstance(values, list) and values:
            lines.append(f"{label}: " + ", ".join(str(value) for value in values))
    return "\n".join(lines)
