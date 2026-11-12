"""Server-owned rolling context for durable project conversations."""
from __future__ import annotations

import copy
import re
from typing import Any

from sqlalchemy.orm import Session

from app import models

KEEP_RECENT = 8
PINNED_CHARS = 4200
PROGRESS_CHARS = 1300
SUMMARY_KEY = "context_summary"

_PIN = re.compile(r"\b(decision|decided|must|never|always|prefer|constraint|requirement|do not|don't|cannot|can't|instead|goal|objective|plan|phase|milestone|deadline|from now on|remember|correction|actually|only|not allowed)\b", re.I)
_HARD = re.compile(r"\b(must|never|always|constraint|requirement|decided|decision|goal|objective|do not|don't|cannot|can't|from now on)\b", re.I)
_PROGRESS = re.compile(r"\b(implemented|fixed|failed|error|blocked|completed|remaining|next|tested|changed|added|removed|running|passed|commit|branch|pull request)\b", re.I)
_PATH_OR_REF = re.compile(r"(?:[A-Za-z]:\\|/)[^\s]{3,}|\b(?:PR|#)\s*\d+", re.I)


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?;])\s+|\n+", text or "") if part.strip()]


def _clip(text: str, limit: int = 500) -> str:
    value = " ".join(text.split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _key(line: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", line.casefold()).strip()


def _empty_summary() -> dict[str, Any]:
    return {"pinned": [], "progress": [], "cursors": {}, "archived": 0}


def _merge(existing: list[str], new: list[str], budget: int) -> tuple[list[str], int]:
    seen = {_key(line) for line in existing}
    merged = list(existing)
    for line in new:
        key = _key(line)
        if key and key not in seen:
            seen.add(key)
            merged.append(line)
    dropped = 0
    while merged and sum(len(line) + 1 for line in merged) > budget:
        victim = next((i for i, line in enumerate(merged) if not _HARD.search(line)), 0)
        merged.pop(victim)
        dropped += 1
    return merged, dropped


def _extract_lines(role: str, content: str) -> tuple[list[str], list[str]]:
    sentences = _sentences(content)
    pinned: list[str] = []
    progress: list[str] = []
    if role == "user":
        for sentence in sentences:
            clipped = _clip(sentence)
            if _PIN.search(sentence):
                pinned.append("- " + clipped)
            elif _PROGRESS.search(sentence) or _PATH_OR_REF.search(sentence):
                progress.append("- user: " + clipped)
        pinned = pinned[:12]
        if not pinned and not progress and sentences:
            progress.append("- user asked: " + _clip(sentences[0]))
    else:
        for sentence in sentences:
            if _PROGRESS.search(sentence) or _PATH_OR_REF.search(sentence):
                progress.append("- assistant: " + _clip(sentence))
    return pinned, progress[:3]


def _messages(db: Session, conversation_id: str) -> list[models.ConversationMessage]:
    return (db.query(models.ConversationMessage)
            .filter(models.ConversationMessage.conversation_id == conversation_id)
            .order_by(models.ConversationMessage.created_at, models.ConversationMessage.id).all())


def _linked_conversation_ids(db: Session, task: models.TaskState) -> set[str]:
    ids = {task.conversation_id}
    events = db.query(models.TaskStateEvent).filter(models.TaskStateEvent.task_state_id == task.id).all()
    for event in events:
        payload = event.payload if isinstance(event.payload, dict) else {}
        for key in ("conversation_id", "previous_conversation_id", "resumed_in_conversation_id"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                ids.add(value)
    return ids


def _fold(summary: dict[str, Any], conversation_id: str, messages: list[models.ConversationMessage], upto: int) -> bool:
    cursors = summary.setdefault("cursors", {})
    cursor = cursors.get(conversation_id) or {}
    last_id = cursor.get("last_id") if isinstance(cursor, dict) else None
    start = 0
    if last_id:
        for index, message in enumerate(messages):
            if message.id == last_id:
                start = index + 1
                break
        else:
            start = min(int(cursor.get("count", 0)), len(messages))
    if upto <= start:
        return False
    pinned: list[str] = []
    progress: list[str] = []
    for message in messages[start:upto]:
        p, g = _extract_lines(message.role, message.content or "")
        pinned.extend(p)
        progress.extend(g)
    summary["pinned"], a = _merge(summary.get("pinned", []), pinned, PINNED_CHARS)
    summary["progress"], b = _merge(summary.get("progress", []), progress, PROGRESS_CHARS)
    summary["archived"] = int(summary.get("archived", 0)) + a + b
    last = messages[upto - 1]
    cursors[conversation_id] = {"last_id": last.id, "count": upto}
    return True


def render_summary(summary: dict[str, Any]) -> str:
    lines = ["Pinned goals, decisions and constraints:", *summary.get("pinned", []),
             "", "Recent progress:", *summary.get("progress", []),
             "", f"Older summary lines archived: {int(summary.get('archived', 0))}"]
    return "\n".join(lines)


def build_conversation_context(db: Session, task_state_id: str | None, conversation_id: str, current_task: str):
    messages = _messages(db, conversation_id)
    available = bool(messages)
    if messages and messages[-1].role == "user" and (messages[-1].content or "").strip() == current_task.strip():
        messages = messages[:-1]
    recent = messages[-KEEP_RECENT:]
    older_upto = len(messages) - len(recent)
    history = [{"role": m.role, "content": m.content or ""} for m in recent]
    summary_text = ""
    task = db.get(models.TaskState, task_state_id) if task_state_id else None
    if task is not None:
        state = copy.deepcopy(dict(task.state_json or {}))
        summary = state.get(SUMMARY_KEY)
        if not isinstance(summary, dict):
            summary = _empty_summary()
        changed = _fold(summary, conversation_id, messages, older_upto)
        for other_id in sorted(_linked_conversation_ids(db, task) - {conversation_id}):
            other = _messages(db, other_id)
            changed = _fold(summary, other_id, other, len(other)) or changed
        if changed:
            state[SUMMARY_KEY] = summary
            task.state_json = state
            db.commit()
        summary_text = render_summary(summary)
    return history, summary_text, available
