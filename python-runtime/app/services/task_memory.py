"""Low-cost, durable task memory.

SQLite is the source of truth. Markdown files are transparent, atomically-written
projections for inspection and recovery; they are never required for retrieval.
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app import models
from app.infra.paths import project_dir
from app.services.evidence import is_verbatim, overlaps
from app.services.task_locks import task_state_lock

logger = logging.getLogger(__name__)

_NEW_TASK_PATTERNS = (
    re.compile(r"^\s*(?:new task|start a new task|switch task|new topic)\s*[:\-]", re.I),
    re.compile(r"\b(?:forget that|start over with a different task|switch to a different task)\b", re.I),
)
_MAX_HEADER_CHARS = 8000
_RESUME_TASK_PATTERN = re.compile(
    r"^\s*(?:resume|continue)\s+(?:the\s+)?task\s*[:#]?\s*([0-9a-f-]{6,36})\s*$",
    re.I,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_explicit_task_switch(message: str) -> bool:
    return any(pattern.search(message) for pattern in _NEW_TASK_PATTERNS)


def _is_resume_latest_task(message: str) -> bool:
    normalized = re.sub(r"[.!?]+$", "", message.casefold().strip())
    return normalized in {
        "continue",
        "resume",
        "pick up",
        "continue our work",
        "continue the task",
        "continue the previous task",
        "resume the previous task",
        "resume previous task",
        "pick up where we left off",
        "continue where we left off",
        "continue from where we left off",
    }


def _resume_task_prefix(message: str) -> str | None:
    match = _RESUME_TASK_PATTERN.match(message)
    return match.group(1).lower() if match else None


def _is_greeting(message: str) -> bool:
    normalized = re.sub(r"[^a-z ]", "", message.casefold()).strip()
    return normalized in {
        "hi", "hello", "hey", "good morning", "good afternoon",
        "good evening", "how are you", "thanks", "thank you",
        "ok", "okay",
    }


def _clean_title(text: str) -> str:
    value = " ".join(text.split())
    return value[:157].rstrip() + ("…" if len(value) > 157 else "")


def _short(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    value = value.strip()
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _render_context(db: Session, row: models.TaskState) -> str:
    state = dict(row.state_json or {})
    last = state.get("last_execution") if isinstance(state.get("last_execution"), dict) else {}
    lines = [
        f"Task: {row.title}",
        f"Task ID: {row.id}",
        f"Status: {row.status}",
        f"State file: .agentforge/memory/tasks/{row.id}/STATE.md",
        f"Original objective: {_short(row.original_objective, 4000)}" + (" [truncated; full objective remains in the task record and STATE.md]" if len(row.original_objective or "") > 4000 else ""),
    ]
    if row.current_instruction and row.current_instruction != row.original_objective:
        lines.append(f"Latest instruction: {_short(row.current_instruction, 300)}")
    recent_instructions = (
        db.query(models.TaskStateEvent)
        .filter(
            models.TaskStateEvent.task_state_id == row.id,
            models.TaskStateEvent.event_type.in_(["task_created", "user_instruction"]),
        )
        .order_by(models.TaskStateEvent.created_at.desc())
        .limit(4)
        .all()
    )
    prior_instructions = [
        event for event in reversed(recent_instructions)
        if event.content not in {row.current_instruction, row.original_objective}
    ][-3:]
    if prior_instructions:
        lines.append("Earlier user instructions:")
        for event in prior_instructions:
            lines.append(f"- {_short(event.content, 160)}")
    other_tasks = (
        db.query(models.TaskState)
        .filter(
            models.TaskState.project_id == row.project_id,
            models.TaskState.agent_id == row.agent_id,
            models.TaskState.id != row.id,
        )
        .order_by(models.TaskState.updated_at.desc())
        .limit(3)
        .all()
    )
    if other_tasks:
        lines.append("Other workstreams in this project:")
        for item in other_tasks:
            lines.append(f"- {item.id[:8]} [{item.status}] {_short(item.title, 100)}")
    recent_executions = state.get("recent_executions")
    if isinstance(recent_executions, list) and len(recent_executions) > 1:
        lines.append("Earlier execution outcomes:")
        for item in recent_executions[-3:-1]:
            if isinstance(item, dict):
                lines.append(
                    f"- {item.get('status', 'unknown')}: {_short(item.get('summary', ''), 180)}"
                )
    plan = state.get("plan") if isinstance(state.get("plan"), dict) else {}
    # Once the plan holds decisions/constraints it is their single source in the
    # prompt (compile_plan_context); listing them here as well only duplicates them.
    plan_owns_rules = bool(plan.get("decisions") or plan.get("constraints"))
    for label, key in (
        *(() if plan_owns_rules else (("Constraints", "constraints"), ("Decisions", "decisions"))),
        ("Completed", "completed"),
        ("Remaining", "remaining"),
        ("Blockers", "blockers"),
    ):
        values = state.get(key)
        if isinstance(values, list) and values:
            compact = "; ".join(_short(value, 240) for value in values[-10:] if isinstance(value, str))
            if compact:
                lines.append(f"{label}: {compact}")
    if state.get("next_action"):
        lines.append(f"Next action: {_short(state['next_action'], 180)}")
    if last:
        lines.append(
            "Last execution: "
            + str(last.get("status", "unknown"))
            + (f" — {_short(last.get('summary', ''), 260)}" if last.get("summary") else "")
        )
    # Raw conversation/execution IDs are not shown to the model: it cannot act on
    # them, and they spend context. They remain in the STATE.md projection.
    rendered = "\n".join(lines)
    return rendered[:_MAX_HEADER_CHARS]


def _write_projection(db: Session, row: models.TaskState) -> None:
    """Write a human-readable task file and compact project task registry."""
    project_root = project_dir(row.project_id).resolve()
    workspace_root = (project_root / "workspace").resolve()
    workspace_root.relative_to(project_root)
    root = (workspace_root / ".agentforge" / "memory").resolve()
    root.relative_to(workspace_root)
    task_dir = root / "tasks" / row.id
    state = dict(row.state_json or {})
    last = state.get("last_execution") if isinstance(state.get("last_execution"), dict) else {}
    events = (
        db.query(models.TaskStateEvent)
        .filter(models.TaskStateEvent.task_state_id == row.id)
        .order_by(models.TaskStateEvent.created_at.desc())
        .limit(12)
        .all()
    )
    lines = [
        f"# {row.title}",
        "",
        f"- Task ID: `{row.id}`",
        f"- Status: {row.status}",
        f"- Version: {row.version}",
        f"- Updated: {row.updated_at.isoformat()}",
        "",
        "## Original objective",
        "",
        row.original_objective,
        "",
        "## Latest instruction",
        "",
        row.current_instruction or row.original_objective,
    ]
    for label, key in (
        ("Constraints", "constraints"),
        ("Decisions", "decisions"),
        ("Completed", "completed"),
        ("Remaining", "remaining"),
        ("Blockers", "blockers"),
    ):
        values = state.get(key)
        if isinstance(values, list) and values:
            lines.extend(["", f"## {label}", ""])
            lines.extend(f"- {_short(value, 300)}" for value in values if isinstance(value, str))
    if state.get("next_action"):
        lines.extend(["", "## Next action", "", _short(state["next_action"], 300)])

    plan = state.get("plan") if isinstance(state.get("plan"), dict) else {}
    plan_nodes = plan.get("nodes") if isinstance(plan.get("nodes"), list) else []
    if plan_nodes or plan.get("root_summary") or plan.get("decisions") or plan.get("constraints") or plan.get("dependencies"):
        lines.extend(["", "## Evolving plan", ""])
        if plan.get("root_summary"):
            lines.extend(["### Root objective summary", "", _short(plan.get("root_summary"), 1800)])
        by_parent: dict[str, list[dict[str, Any]]] = {}
        for node in plan_nodes:
            if isinstance(node, dict):
                by_parent.setdefault(str(node.get("parent_id") or row.id), []).append(node)

        def append_plan(parent_id: str, depth: int, seen: set[str]) -> None:
            if depth > 500:
                return
            for node in by_parent.get(parent_id, []):
                node_id = str(node.get("id") or "")
                if not node_id or node_id in seen:
                    continue
                seen.add(node_id)
                indent = "  " * depth
                lines.append(
                    f"{indent}- [{node.get('status', 'proposed')}] "
                    f"{node.get('type', 'task')}: {_short(node.get('title', ''), 120)}"
                )
                append_plan(node_id, depth + 1, seen)

        append_plan(row.id, 0, set())
        node_titles = {
            str(node.get("id")): _short(node.get("title", ""), 120)
            for node in plan_nodes if isinstance(node, dict)
        }
        dependencies = plan.get("dependencies") if isinstance(plan.get("dependencies"), list) else []
        if dependencies:
            lines.extend(["", "### Dependencies", ""])
            for edge in dependencies[-30:]:
                if not isinstance(edge, dict):
                    continue
                dependent = node_titles.get(str(edge.get("node_id")), "unknown task")
                prerequisite = node_titles.get(str(edge.get("depends_on_id")), "unknown task")
                lines.append(f"- {dependent} depends on {prerequisite}")
        for label, key, accepted_only in (
            ("Accepted user decisions", "decisions", True),
            ("Explicit user constraints", "constraints", False),
        ):
            items = plan.get(key) if isinstance(plan.get(key), list) else []
            if accepted_only:
                items = [item for item in items if isinstance(item, dict) and item.get("status") == "accepted"]
            if items:
                lines.extend(["", f"### {label}", ""])
                lines.extend(
                    f"- {_short(item.get('text', ''), 300)}"
                    for item in items if isinstance(item, dict)
                )
    if last:
        lines.extend([
            "",
            "## Last execution",
            "",
            f"- Status: {last.get('status', 'unknown')}",
            f"- Execution ID: `{last.get('execution_id', '')}`",
        ])
        if last.get("summary"):
            lines.extend(["", _short(last["summary"], 1200)])
        if last.get("error"):
            lines.extend(["", f"Error: {_short(last['error'], 500)}"])
    lines.extend(["", "## Recent task events", ""])
    for event in reversed(events):
        stamp = event.created_at.isoformat() if event.created_at else ""
        detail = _short(event.content, 500)
        lines.append(f"- [{stamp}] **{event.event_type}**: {detail}")
    _atomic_write(task_dir / "STATE.md", "\n".join(lines).rstrip() + "\n")

    rows = (
        db.query(models.TaskState)
        .filter(models.TaskState.project_id == row.project_id)
        .order_by(models.TaskState.updated_at.desc())
        .limit(100)
        .all()
    )
    active_rows = (
        db.query(models.TaskState)
        .filter(
            models.TaskState.project_id == row.project_id,
            models.TaskState.status == "active",
        )
        .all()
    )
    registry = {
        "schema_version": 1,
        "updated_at": _now().isoformat(),
        "active_tasks_by_conversation": {
            item.conversation_id: item.id for item in active_rows
        },
        "tasks": [
            {
                "id": item.id,
                "conversation_id": item.conversation_id,
                "title": item.title,
                "status": item.status,
                "version": item.version,
                "updated_at": item.updated_at.isoformat(),
                "state_file": f"tasks/{item.id}/STATE.md",
            }
            for item in rows
        ],
    }
    _atomic_write(root / "registry.json", json.dumps(registry, ensure_ascii=False, indent=2) + "\n")


def prepare_task_state(
    db: Session,
    conversation: models.Conversation,
    user_message: str,
) -> tuple[str | None, str]:
    """Persist a user turn before model execution and return (task id, compact header).

    A normal follow-up updates only the latest instruction. The original objective
    is immutable unless the user explicitly starts/switches tasks.
    """
    message = user_message.strip()
    if not message:
        return None, ""

    now = _now()
    row = (
        db.query(models.TaskState)
        .filter(
            models.TaskState.conversation_id == conversation.id,
            models.TaskState.status == "active",
        )
        .order_by(models.TaskState.updated_at.desc())
        .first()
    )
    resume_prefix = _resume_task_prefix(message)
    implicit_resume = False
    if (
        not resume_prefix
        and row is None
        and not _is_explicit_task_switch(message)
        and not _is_greeting(message)
    ):
        # Continue the most recently updated active workstream when a new chat
        # starts without an explicit task switch. Preserve the incoming message
        # as a user instruction; users can disambiguate with "New task:" or
        # explicitly resume another workstream by ID.
        candidate = (
            db.query(models.TaskState)
            .filter(
                models.TaskState.project_id == conversation.project_id,
                models.TaskState.agent_id == conversation.agent_id,
                models.TaskState.status == "active",
            )
            .order_by(models.TaskState.updated_at.desc(), models.TaskState.id.desc())
            .first()
        )
        if candidate is not None:
            resume_prefix = candidate.id[:8]
            implicit_resume = True
    if resume_prefix:
        matches = (
            db.query(models.TaskState)
            .filter(
                models.TaskState.project_id == conversation.project_id,
                models.TaskState.agent_id == conversation.agent_id,
                models.TaskState.id.like(f"{resume_prefix}%"),
            )
            .limit(2)
            .all()
        )
        if len(matches) != 1:
            raise ValueError(
                "Could not uniquely identify that task. Use the 8-character ID shown in the task registry."
            )
        if len(matches) == 1:
            target = matches[0]
            if row is not None and row.id != target.id:
                row.status = "paused"
                row.updated_at = now
                row.version += 1
                db.add(models.TaskStateEvent(
                    id=models._uuid(),
                    task_state_id=row.id,
                    event_type="task_paused",
                    content=f"Paused to resume task {target.id[:8]}.",
                    payload={"reason": "resume_other_task"},
                    created_at=now,
                ))
            previous_conversation_id = target.conversation_id
            target.status = "active"
            # A task is a project workstream, not a single chat. Rebind it to
            # the conversation that is now continuing the work.
            target.conversation_id = conversation.id
            carries_instruction = implicit_resume and not _is_resume_latest_task(message)
            if carries_instruction:
                target.current_instruction = message
            else:
                target.current_instruction = (
                    _short((target.state_json or {}).get("next_action") or "", 300)
                    or target.original_objective
                )
            target.updated_at = now
            target.version += 1
            db.add(models.TaskStateEvent(
                id=models._uuid(),
                task_state_id=target.id,
                event_type="task_resumed",
                content=f"Resumed in conversation {conversation.id}.",
                payload={
                    "resumed_by_prefix": resume_prefix,
                    "implicit": implicit_resume,
                    "previous_conversation_id": previous_conversation_id,
                    "resumed_in_conversation_id": conversation.id,
                },
                created_at=now,
            ))
            if carries_instruction:
                db.add(models.TaskStateEvent(
                    id=models._uuid(),
                    task_state_id=target.id,
                    event_type="user_instruction",
                    content=_short(message, 4000),
                    payload={"message_length": len(message), "conversation_id": conversation.id},
                    created_at=now,
                ))
            db.commit()
            db.refresh(target)
            context = _render_context(db, target)
            try:
                if row is not None and row.id != target.id:
                    _write_projection(db, row)
                _write_projection(db, target)
            except Exception:
                logger.exception("Could not update task-memory projection after resuming %s", target.id)
            return target.id, context

    explicit_switch = _is_explicit_task_switch(message)
    paused_row = None
    if row is not None and explicit_switch:
        paused_row = row
        row.status = "paused"
        row.version += 1
        row.updated_at = now
        row = None

    if paused_row is not None:
        db.add(models.TaskStateEvent(
            id=models._uuid(),
            task_state_id=paused_row.id,
            event_type="task_paused",
            content=f"Paused when a new task was started: {_short(message, 300)}",
            payload={"reason": "explicit_task_switch"},
            created_at=now,
        ))

    if row is None:
        objective = message
        if not explicit_switch:
            first_user_message = (
                db.query(models.ConversationMessage)
                .filter(
                    models.ConversationMessage.conversation_id == conversation.id,
                    models.ConversationMessage.role == "user",
                )
                .order_by(models.ConversationMessage.created_at, models.ConversationMessage.id)
                .first()
            )
            if (
                first_user_message
                and first_user_message.content.strip()
                and not _is_greeting(first_user_message.content)
            ):
                objective = first_user_message.content.strip()
        row = models.TaskState(
            id=models._uuid(),
            conversation_id=conversation.id,
            project_id=conversation.project_id,
            agent_id=conversation.agent_id,
            title=_clean_title(objective),
            original_objective=objective,
            current_instruction=message,
            status="active",
            state_json={
                "constraints": [],
                "decisions": [],
                "completed": [],
                "remaining": [],
                "blockers": [],
                "last_execution": None,
            },
            version=1,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.flush()
        event_type = "task_created"
    else:
        row.current_instruction = message
        row.updated_at = now
        row.version += 1
        event_type = "user_instruction"

    if event_type == "task_created" and row.original_objective != message:
        db.add(models.TaskStateEvent(
            id=models._uuid(),
            task_state_id=row.id,
            event_type="task_created",
            content=_short(row.original_objective, 4000),
            payload={"backfilled_from_conversation": True},
            created_at=now,
        ))
        event_type = "user_instruction"
    db.add(models.TaskStateEvent(
        id=models._uuid(),
        task_state_id=row.id,
        event_type=event_type,
        content=_short(message, 4000),
        payload={"message_length": len(message), "conversation_id": conversation.id},
        created_at=now,
    ))
    db.commit()
    db.refresh(row)
    context = _render_context(db, row)
    try:
        if paused_row is not None:
            _write_projection(db, paused_row)
        _write_projection(db, row)
    except Exception:
        logger.exception("Could not update task-memory Markdown projection for %s", row.id)
    return row.id, context


def bind_task_state_to_execution(task_state_id: str | None, execution_id: str) -> None:
    """Persist which task a running execution belongs to, even after task switches."""
    if not task_state_id:
        return
    from app.db import SessionLocal

    try:
        with SessionLocal() as db:
            row = db.get(models.TaskState, task_state_id)
            execution = db.get(models.Execution, execution_id)
            if row is None or execution is None:
                return
            db.add(models.TaskStateEvent(
                id=models._uuid(),
                task_state_id=row.id,
                event_type="execution_bound",
                content=f"Execution {execution_id} is working on this task.",
                source_execution_id=execution_id,
                payload={"execution_id": execution_id},
                created_at=_now(),
            ))
            db.commit()
    except Exception:
        # Binding improves routing for live messages, but must never strand an
        # execution that has already been accepted by the execution manager.
        logger.exception("Could not bind execution %s to task state %s", execution_id, task_state_id)


def record_live_task_instruction(
    conversation_id: str,
    execution_id: str,
    user_message: str,
) -> None:
    """Persist a successfully-delivered live instruction on the running task."""
    from app.db import SessionLocal

    message = user_message.strip()
    if not message:
        return
    now = _now()
    try:
        with SessionLocal() as db:
            conversation = db.get(models.Conversation, conversation_id)
            if conversation is None:
                return
            bound_event = (
                db.query(models.TaskStateEvent)
                .filter(
                    models.TaskStateEvent.source_execution_id == execution_id,
                    models.TaskStateEvent.event_type == "execution_bound",
                )
                .order_by(models.TaskStateEvent.created_at.desc())
                .first()
            )
            row = db.get(models.TaskState, bound_event.task_state_id) if bound_event else None
            if row is None:
                row = (
                    db.query(models.TaskState)
                    .filter(
                        models.TaskState.conversation_id == conversation_id,
                        models.TaskState.status == "active",
                    )
                    .order_by(models.TaskState.updated_at.desc())
                    .first()
                )
            if row is None:
                first_user_message = (
                    db.query(models.ConversationMessage)
                    .filter(
                        models.ConversationMessage.conversation_id == conversation_id,
                        models.ConversationMessage.role == "user",
                    )
                    .order_by(models.ConversationMessage.created_at, models.ConversationMessage.id)
                    .first()
                )
                objective = (
                    first_user_message.content.strip()
                    if (
                        first_user_message
                        and first_user_message.content.strip()
                        and not _is_greeting(first_user_message.content)
                    )
                    else message
                )
                row = models.TaskState(
                    id=models._uuid(),
                    conversation_id=conversation.id,
                    project_id=conversation.project_id,
                    agent_id=conversation.agent_id,
                    title=_clean_title(objective),
                    original_objective=objective,
                    current_instruction=message,
                    status="active",
                    state_json={
                        "constraints": [],
                        "decisions": [],
                        "completed": [],
                        "remaining": [],
                        "blockers": [],
                        "last_execution": None,
                    },
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
                db.add(row)
                db.flush()
                db.add(models.TaskStateEvent(
                    id=models._uuid(),
                    task_state_id=row.id,
                    event_type="task_created",
                    content=_short(objective, 4000),
                    payload={"created_from_live_instruction": True},
                    created_at=now,
                ))
            else:
                row.current_instruction = message
                row.updated_at = now
                row.version += 1
            db.add(models.TaskStateEvent(
                id=models._uuid(),
                task_state_id=row.id,
                event_type="live_user_instruction",
                content=_short(message, 4000),
                source_execution_id=execution_id,
                payload={"message_length": len(message), "conversation_id": conversation_id},
                created_at=now,
            ))
            db.commit()
            try:
                _write_projection(db, row)
            except Exception:
                logger.exception("Could not update task-memory projection for live message %s", execution_id)
    except Exception:
        logger.exception("Could not persist live task instruction for execution %s", execution_id)


def record_task_execution_result(
    task_state_id: str | None,
    execution_id: str,
    status: str,
    final_output: str = "",
    error: str | None = None,
) -> None:
    """Persist actual run status and output excerpt without a separate LLM summary."""
    if not task_state_id:
        return
    from app.db import SessionLocal

    now = _now()
    with task_state_lock(task_state_id), SessionLocal() as db:
        row = db.get(models.TaskState, task_state_id)
        if row is None:
            return
        state = dict(row.state_json or {})
        latest_execution = {
            "execution_id": execution_id,
            "status": status,
            "summary": _short(final_output, 700),
            "error": _short(error or "", 400),
            "recorded_at": now.isoformat(),
        }
        recent_executions = state.get("recent_executions")
        if not isinstance(recent_executions, list):
            recent_executions = []
        state["recent_executions"] = (recent_executions + [latest_execution])[-3:]
        state["last_execution"] = latest_execution
        row.state_json = state
        row.updated_at = now
        row.version += 1
        db.add(models.TaskStateEvent(
            id=models._uuid(),
            task_state_id=row.id,
            event_type="execution_result",
            content=_short(final_output or error or status, 1200),
            source_execution_id=execution_id,
            payload={"status": status},
            created_at=now,
        ))
        db.commit()
        try:
            _write_projection(db, row)
        except Exception:
            logger.exception("Could not update task-memory projection after execution %s", execution_id)


def _normalized_items(values: Any, *, limit: int = 12) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        item = _short(value, 240)
        key = item.casefold()
        if item and key not in seen:
            seen.add(key)
            result.append(item)
    return result[-limit:]


def _append_unique(existing: Any, additions: Any) -> list[str]:
    values = _normalized_items(existing)
    seen = {item.casefold() for item in values}
    for item in _normalized_items(additions, limit=5):
        if item.casefold() not in seen:
            values.append(item)
            seen.add(item.casefold())
    return values[-12:]


def _would_create_dependency_cycle(
    dependencies: list[dict[str, Any]],
    node_id: str,
    depends_on_id: str,
) -> bool:
    adjacency: dict[str, list[str]] = {}
    for edge in dependencies:
        if isinstance(edge, dict):
            adjacency.setdefault(str(edge.get("node_id")), []).append(str(edge.get("depends_on_id")))
    pending = [depends_on_id]
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if current == node_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        pending.extend(adjacency.get(current, []))
    return False


def apply_task_state_update(
    task_state_id: str,
    execution_id: str,
    patch: dict[str, Any],
) -> dict[str, Any]:
    """Apply a validated, bounded agent-authored update without another LLM call."""
    from app.db import SessionLocal

    now = _now()
    with task_state_lock(task_state_id), SessionLocal() as db:
        row = db.get(models.TaskState, task_state_id)
        if row is None:
            raise ValueError("The task state no longer exists.")
        execution = db.get(models.Execution, execution_id)
        bound = (
            db.query(models.TaskStateEvent)
            .filter(
                models.TaskStateEvent.task_state_id == task_state_id,
                models.TaskStateEvent.source_execution_id == execution_id,
                models.TaskStateEvent.event_type == "execution_bound",
            )
            .first()
        )
        if execution is None or execution.status != "running" or bound is None:
            raise ValueError("This execution is not authorized to update that task's memory.")
        if row.status != "active":
            raise ValueError("This task is no longer active; do not update its memory.")
        state = dict(row.state_json or {})
        changed: list[str] = []

        user_events = (
            db.query(models.TaskStateEvent)
            .filter(
                models.TaskStateEvent.task_state_id == task_state_id,
                models.TaskStateEvent.event_type.in_(["task_created", "user_instruction", "live_user_instruction"]),
            )
            .order_by(models.TaskStateEvent.created_at.asc())
            .all()
        )
        user_texts = [row.original_objective or "", row.current_instruction or ""] + [
            event.content for event in user_events if isinstance(event.content, str)
        ]

        def user_said(item: str) -> bool:
            # The agent paraphrases; accept a close restatement of one real user message.
            return any(is_verbatim(item, text) or overlaps(item, text) for text in user_texts if text)

        accepted_constraints: list[str] = []
        accepted_decisions: list[str] = []
        ignored_constraints: list[str] = []
        plan_decisions = list((state.get("plan") or {}).get("decisions") or [])
        plan_constraints = list((state.get("plan") or {}).get("constraints") or [])
        plan_decisions_added: list[dict[str, Any]] = []
        plan_constraints_added: list[dict[str, Any]] = []
        ignored_decisions: list[str] = []

        for key in ("constraints", "decisions"):
            incoming = _normalized_items(patch.get(f"{key}_add"), limit=5)
            accepted = [item for item in incoming if user_said(item)]
            ignored = [item for item in incoming if not user_said(item)]
            if accepted:
                state[key] = _append_unique(state.get(key), accepted)
                changed.append(key)
            if key == "constraints":
                accepted_constraints, ignored_constraints = accepted, ignored
            else:
                accepted_decisions, ignored_decisions = accepted, ignored

        for item in accepted_decisions:
            if not any(
                decision.get("text", "").casefold() == item.casefold() and decision.get("status") == "accepted"
                for decision in plan_decisions if isinstance(decision, dict)
            ):
                decision = {
                    "id": models._uuid(), "text": item, "status": "accepted",
                    "authority": "user", "evidence": item, "created_at": now.isoformat(),
                }
                plan_decisions.append(decision)
                plan_decisions_added.append(decision)
        for item in accepted_constraints:
            if not any(
                constraint.get("text", "").casefold() == item.casefold()
                for constraint in plan_constraints if isinstance(constraint, dict)
            ):
                constraint = {
                    "id": models._uuid(), "text": item, "evidence": item,
                    "created_at": now.isoformat(),
                }
                plan_constraints.append(constraint)
                plan_constraints_added.append(constraint)

        completed_incoming = patch.get("completed_add") or []
        if completed_incoming:
            state["completed"] = _append_unique(state.get("completed"), completed_incoming)
            changed.append("completed")

        for key in ("remaining", "blockers"):
            if key in patch and patch[key] is not None:
                state[key] = _normalized_items(patch[key])
                changed.append(key)

        if "completed_add" in patch and patch.get("completed_add"):
            completed_keys = {item.casefold() for item in state.get("completed", [])}
            remaining = _normalized_items(state.get("remaining"))
            state["remaining"] = [item for item in remaining if item.casefold() not in completed_keys]
            if "remaining" not in changed:
                changed.append("remaining")

        if "next_action" in patch:
            state["next_action"] = _short(patch.get("next_action") or "", 300)
            changed.append("next_action")

        # Only this execution-bound tool path may mark plan nodes complete.
        # The cheap interpreter is explicitly forbidden from asserting completion.
        completed_plan_nodes: list[dict[str, str]] = []
        completed_items = _normalized_items(patch.get("completed_add"), limit=5)
        plan = state.get("plan") if isinstance(state.get("plan"), dict) else {}
        plan_nodes = plan.get("nodes") if isinstance(plan.get("nodes"), list) else []
        for node in plan_nodes:
            if not isinstance(node, dict) or node.get("status") == "completed":
                continue
            title = _short(node.get("title"), 120).casefold()
            matched = next(
                (item for item in completed_items if title and (
                    title == item.casefold() or title in item.casefold()
                )),
                None,
            )
            if matched:
                node["status"] = "completed"
                node["completed_at"] = now.isoformat()
                node["verified_by_execution_id"] = execution_id
                node["updated_at"] = now.isoformat()
                node["version"] = int(node.get("version", 1)) + 1
                completed_plan_nodes.append({"node_id": str(node.get("id", "")), "title": _short(node.get("title"), 120)})
        plan_nodes_added: list[dict[str, Any]] = []
        plan_dependencies_added: list[dict[str, Any]] = []
        plan_changed = bool(completed_plan_nodes or plan_decisions_added or plan_constraints_added)
        existing_nodes = {
            str(node.get("id")): node for node in plan_nodes if isinstance(node, dict)
        }
        ref_to_id = {"root": task_state_id, **{node_id: node_id for node_id in existing_nodes}}
        for draft in (patch.get("plan_nodes_add") or [])[:8]:
            if not isinstance(draft, dict):
                continue
            ref = _short(draft.get("ref"), 64)
            title = _short(draft.get("title"), 120)
            node_type = draft.get("type")
            parent_ref = _short(draft.get("parent_ref") or "root", 64)
            parent_id = ref_to_id.get(parent_ref)
            if not ref or ref in ref_to_id or not title or not parent_id:
                continue
            if node_type not in {"goal", "phase", "subgoal", "task", "milestone"}:
                continue
            if any(
                node.get("parent_id") == parent_id
                and _short(node.get("title"), 120).casefold() == title.casefold()
                for node in plan_nodes if isinstance(node, dict)
            ):
                continue
            node = {
                "id": models._uuid(),
                "parent_id": parent_id,
                "type": node_type,
                "title": title,
                "objective": _short(draft.get("objective"), 500),
                "status": "active",
                "source": "agent",
                "evidence": "",
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "version": 1,
            }
            plan_nodes.append(node)
            existing_nodes[node["id"]] = node
            ref_to_id[ref] = node["id"]
            plan_nodes_added.append(node)
            plan_changed = True

        dependencies = plan.get("dependencies") if isinstance(plan.get("dependencies"), list) else []
        for draft in (patch.get("plan_dependencies_add") or [])[:8]:
            if not isinstance(draft, dict):
                continue
            node_id = ref_to_id.get(_short(draft.get("node_ref"), 64))
            depends_on_id = ref_to_id.get(_short(draft.get("depends_on_ref"), 64))
            if (
                not node_id or not depends_on_id or node_id == depends_on_id
                or _would_create_dependency_cycle(dependencies, node_id, depends_on_id)
            ):
                continue
            if any(
                edge.get("node_id") == node_id and edge.get("depends_on_id") == depends_on_id
                for edge in dependencies if isinstance(edge, dict)
            ):
                continue
            edge = {
                "id": models._uuid(),
                "node_id": node_id,
                "depends_on_id": depends_on_id,
                "reason": _short(draft.get("reason"), 240),
                "source": "agent",
                "created_at": now.isoformat(),
            }
            dependencies.append(edge)
            plan_dependencies_added.append(edge)
            plan_changed = True

        if plan_changed:
            plan.setdefault("schema_version", 1)
            plan.setdefault("root_summary", "")
            plan["decisions"] = plan_decisions[-80:]
            plan["constraints"] = plan_constraints[-80:]
            plan["nodes"] = plan_nodes[-500:]
            plan["dependencies"] = dependencies[-300:]
            plan["updated_at"] = now.isoformat()
            state["plan"] = plan
            if "plan" not in changed:
                changed.append("plan")

        if not changed:
            return {
                "updated": False,
                "reason": "No verified task-state fields were supplied.",
                "version": row.version,
                "ignored_unverified_constraints": ignored_constraints,
                "ignored_unverified_decisions": ignored_decisions,
            }

        row.state_json = state
        row.updated_at = now
        row.version += 1
        note = _short(patch.get("note") or "", 300)
        if not note:
            note = "Updated task memory: " + ", ".join(dict.fromkeys(changed))
        event_payload = {
            key: patch.get(key, patch.get(f"{key}_add"))
            for key in ("completed", "remaining", "blockers", "next_action")
            if key in patch or f"{key}_add" in patch
        }
        if accepted_constraints:
            event_payload["accepted_constraints"] = accepted_constraints
        if accepted_decisions:
            event_payload["accepted_decisions"] = accepted_decisions
        if plan_decisions_added:
            event_payload["plan_decisions_added"] = plan_decisions_added
        if plan_constraints_added:
            event_payload["plan_constraints_added"] = plan_constraints_added
        if ignored_constraints:
            event_payload["ignored_unverified_constraints"] = ignored_constraints
        if ignored_decisions:
            event_payload["ignored_unverified_decisions"] = ignored_decisions
        if completed_plan_nodes:
            event_payload["plan_nodes_completed"] = completed_plan_nodes
        if plan_nodes_added:
            event_payload["plan_nodes_added"] = plan_nodes_added
        if plan_dependencies_added:
            event_payload["plan_dependencies_added"] = plan_dependencies_added
        db.add(models.TaskStateEvent(
            id=models._uuid(),
            task_state_id=row.id,
            event_type="agent_state_update",
            content=note,
            source_execution_id=execution_id,
            payload=event_payload,
            created_at=now,
        ))
        db.commit()
        version = row.version
        next_action = state.get("next_action", "")
        try:
            _write_projection(db, row)
        except Exception:
            logger.exception("Could not update task-memory projection for %s", row.id)
        return {
            "updated": True,
            "task_id": row.id,
            "version": version,
            "updated_fields": list(dict.fromkeys(changed)),
            "next_action": next_action,
            "ignored_unverified_constraints": ignored_constraints,
            "ignored_unverified_decisions": ignored_decisions,
        }
