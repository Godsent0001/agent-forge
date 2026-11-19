"""On-demand backfill of older conversation turns into factual-detail files.

A job is created only after a user sends a message to an existing conversation.
The processor is durable/checkpointed and never runs in the request's response path.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

from app import models
from app.core.llm.adapter import complete
from app.core.llm.model_names import litellm_model
from app.core.llm.types import LLMParams
from app.db import SessionLocal
from app.infra.paths import data_dir, project_dir
from app.services.ingestion_queue import IngestionJob, IngestionQueue

logger = logging.getLogger(__name__)
_QUEUE = IngestionQueue(data_dir() / "queues" / "conversation_backfill.sqlite3", lease_seconds=180)
_BATCH_MESSAGES = 18
_MAX_MESSAGE_CHARS = 7000


def _facts_dir(project_id: str, conversation_id: str) -> Path:
    root = (project_dir(project_id) / ".agentforge" / "conversation_facts" / conversation_id).resolve()
    allowed = (project_dir(project_id) / ".agentforge" / "conversation_facts").resolve()
    if not root.is_relative_to(allowed):
        raise ValueError("Invalid conversation facts path")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")[:48]
    return value or "related-details"


def enqueue_backfill(conversation_id: str, trigger_message_id: str) -> str | None:
    """Queue one idempotent backfill generation, keyed by the message that triggered it."""
    with SessionLocal() as db:
        conversation = db.get(models.Conversation, conversation_id)
        if conversation is None:
            return None
        agent = db.get(models.Agent, conversation.agent_id)
        if agent is None or not agent.model or not agent.provider or agent.provider.casefold() == "fake":
            return None
        prior_count = db.query(models.ConversationMessage).filter(
            models.ConversationMessage.conversation_id == conversation_id,
            models.ConversationMessage.id != trigger_message_id,
            models.ConversationMessage.role.in_(["user", "assistant"]),
        ).count()
        # A brand-new chat has no history to backfill.
        if prior_count == 0:
            return None
        payload = {
            "conversation_id": conversation.id,
            "project_id": conversation.project_id,
            "agent_id": conversation.agent_id,
            "provider": agent.provider,
            "model": agent.model,
            "trigger_message_id": trigger_message_id,
        }
    digest = hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()
    # One resumable job per conversation. A later user message reopens a completed
    # job so only conversations the user returns to incur further extraction cost.
    job = _QUEUE.enqueue(
        "conversation_backfill", payload, content_hash=digest, reopen_completed=True
    )
    return job.id


def _parse_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Backfill model did not return a JSON object")
    result = json.loads(text[start:end + 1])
    if not isinstance(result, dict):
        raise ValueError("Backfill response must be a JSON object")
    return result


def _store_groups(project_id: str, conversation_id: str, groups: list[Any], valid_ids: set[str]) -> int:
    root = _facts_dir(project_id, conversation_id)
    written = 0
    for group in groups:
        if not isinstance(group, dict):
            continue
        title = str(group.get("title") or "").strip()[:120]
        description = str(group.get("description") or "").strip()[:1200]
        facts = group.get("facts")
        if not title or not description or not isinstance(facts, list):
            continue
        file_id = _slug(str(group.get("file_id") or title))
        path = root / f"{file_id}.json"
        existing: dict[str, Any] = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text("utf-8"))
            except (OSError, ValueError):
                logger.warning("Ignoring unreadable conversation fact file %s", path)
        stored = existing.get("facts", []) if isinstance(existing, dict) else []
        known = {
            (str(item.get("source_message_id")), str(item.get("text")))
            for item in stored if isinstance(item, dict)
        }
        for fact in facts:
            if not isinstance(fact, dict):
                continue
            text = str(fact.get("text") or "").strip()[:4000]
            sources = fact.get("source_message_ids")
            if not text or not isinstance(sources, list):
                continue
            # Provenance is mandatory: discard any claim not tied to this batch.
            source_ids = [str(item) for item in sources if str(item) in valid_ids]
            for source_id in source_ids:
                key = (source_id, text)
                if key in known:
                    continue
                stored.append({"source_message_id": source_id, "text": text})
                known.add(key)
        if not stored:
            continue
        payload = {
            "id": file_id,
            "title": title,
            "description": description,
            "facts": stored[-1000:],
        }
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(path)
        written += 1
    return written


def _process_batch(job: IngestionJob, batch_size: int) -> tuple[str | None, bool, dict[str, Any] | None]:
    payload = job.payload
    conversation_id = str(payload["conversation_id"])
    with SessionLocal() as db:
        trigger = db.get(models.ConversationMessage, str(payload["trigger_message_id"]))
        if trigger is None or trigger.conversation_id != conversation_id:
            return None, True, {"skipped": "trigger_message_missing"}
        ordered = (
            db.query(models.ConversationMessage)
            .filter(
                models.ConversationMessage.conversation_id == conversation_id,
                models.ConversationMessage.role.in_(["user", "assistant"]),
            )
            .order_by(models.ConversationMessage.created_at, models.ConversationMessage.id)
            .all()
        )
        offset = int(job.cursor or 0)
        batch = ordered[offset:offset + min(batch_size, _BATCH_MESSAGES)]
        if not batch:
            return None, True, {"messages_processed": offset}
        records = [{"id": item.id, "role": item.role, "content": (item.content or "")[:_MAX_MESSAGE_CHARS]} for item in batch]
        valid_ids = {item["id"] for item in records}
    prompt = (
        "Extract durable factual details from this historical user/assistant conversation batch. "
        "Group details by their actual relationship; one batch may produce several files. "
        "Do not combine unrelated subjects. Preserve exact values, filenames, paths, ports, dates, "
        "technical choices, reasons, corrections and user-agent agreements. Include small but useful "
        "conversational details when they affect continuity. Do not invent, infer missing values, or "
        "turn assistant suggestions into user decisions. Keep assistant statements only when they "
        "record verified outcomes or an explicit agreement. Each fact MUST cite one or more message IDs "
        "from this batch. Return JSON only with {groups:[{file_id,title,description,facts:[{text,source_message_ids}]}]}. "
        "Descriptions must precisely explain what each file contains so another agent can decide whether "
        "to load it. If no durable details exist, return {groups:[]}."
    )
    async def call():
        return await complete(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(records, ensure_ascii=False)},
            ],
            params=LLMParams(timeout_s=60, temperature=0, max_tokens=3000),
            model=litellm_model(str(payload["provider"]), str(payload["model"])),
            provider=str(payload["provider"]),
            max_retries=1,
        )
    turn = asyncio.run(call())
    result = _parse_json(turn.text or "")
    groups = result.get("groups") if isinstance(result.get("groups"), list) else []
    written = _store_groups(str(payload["project_id"]), conversation_id, groups, valid_ids)
    next_offset = offset + len(batch)
    done = next_offset >= len(ordered)
    return (None if done else str(next_offset), done, {
        "messages_processed": next_offset, "fact_files_written": written,
    })


def run_backfill_job(job_id: str) -> None:
    """Drain only this job in bounded batches; the API response is already returned."""
    worker_id = f"conversation-backfill-{job_id}"
    try:
        while True:
            current = _QUEUE.get(job_id)
            if current is None or current.status in {"completed", "failed", "cancelled"}:
                return
            result = _QUEUE.process_job(
                job_id, _process_batch, batch_size=_BATCH_MESSAGES, worker_id=worker_id,
            )
            if result is None or result.id != job_id:
                return
            if result.status in {"completed", "failed", "cancelled"}:
                return
    except Exception:
        logger.exception("Conversation backfill failed for job %s", job_id)


def list_fact_descriptions(project_id: str, conversation_id: str) -> list[dict[str, str]]:
    root = _facts_dir(project_id, conversation_id)
    descriptions: list[dict[str, str]] = []
    for path in sorted(root.glob("*.json")):
        try:
            item = json.loads(path.read_text("utf-8"))
            if item.get("id") and item.get("title") and item.get("description"):
                descriptions.append({
                    "id": str(item["id"]),
                    "title": str(item["title"])[:120],
                    "description": str(item["description"])[:1200],
                })
        except (OSError, ValueError, TypeError):
            logger.warning("Could not read conversation fact description %s", path)
    return descriptions


def load_fact_file(project_id: str, conversation_id: str, file_id: str) -> dict[str, Any] | None:
    if not re.fullmatch(r"[a-z0-9-]{1,48}", file_id or ""):
        return None
    path = _facts_dir(project_id, conversation_id) / f"{file_id}.json"
    try:
        item = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return item if isinstance(item, dict) and item.get("id") == file_id else None
