"""
Agent memory: recent entries verbatim, older entries folded into a
rolling summary — same shape as OpenClaw's compaction (keep the recent
window intact, summarize what falls outside it, never delete the
underlying record). Fixes the earlier implementation's core problem:
reading and re-sending *every* memory entry on every single run, with
no bound on prompt size or token cost.

Split into pure functions (testable without a DB) and a thin DB-
integration wrapper (read_memory / write_memory), so the compaction
and truncation logic can be verified in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

# Tunables. Small on purpose for a desktop app talking to SQLite — an
# agent that runs constantly can raise RECENT_KEEP / MAX_MEMORY_CHARS,
# but the defaults keep prompt cost flat regardless of agent age.
RECENT_KEEP = 8            # entries always sent verbatim, newest first in age
COMPACT_TRIGGER = 12       # once this many un-summarized older entries pile up, compact
MAX_MEMORY_CHARS = 3000    # hard cap on the final assembled memory string


class EntryLike(Protocol):
    id: str
    content: str
    created_at: datetime
    summarized: bool


@dataclass
class CompactionPlan:
    to_summarize: list[EntryLike]
    recent: list[EntryLike]


def plan_compaction(entries: list[EntryLike]) -> CompactionPlan:
    """
    entries must be ordered oldest -> newest.
    Splits into: the always-verbatim recent window, and (if the older
    un-summarized backlog has crossed COMPACT_TRIGGER) the batch that
    should be folded into the summary this run.
    """
    recent = entries[-RECENT_KEEP:] if entries else []
    older = entries[:-RECENT_KEEP] if len(entries) > RECENT_KEEP else []
    older_unsummarized = [e for e in older if not e.summarized]

    to_summarize = older_unsummarized if len(older_unsummarized) >= COMPACT_TRIGGER else []
    return CompactionPlan(to_summarize=to_summarize, recent=recent)


def assemble_memory_context(summary: str, recent: list[EntryLike],
                             max_chars: int = MAX_MEMORY_CHARS) -> str:
    """
    Builds the final [MEMORY] string: summary first, then recent entries
    verbatim, oldest of the recent window first. If the combined length
    would exceed max_chars, drops the OLDEST recent entries first.
    """
    if not summary and not recent:
        return "(no memory yet)"

    header = "ARCHIVED HISTORICAL MEMORY LOG (FOR BACKGROUND REFERENCE ONLY):\n- Note: The entries below are past archived interactions. Do NOT adopt old tasks, topics, or scripts from this archive unless the current user instruction specifically requests them."
    summary_block = f"[SUMMARY OF EARLIER HISTORY]\n{summary}" if summary else ""

    kept = list(recent)
    while kept:
        recent_block = "\n".join(f"- {e.content}" for e in kept)
        parts = [p for p in (header, summary_block, recent_block) if p]
        combined = "\n\n".join(parts)
        if len(combined) <= max_chars:
            return combined
        kept = kept[1:]  # drop the oldest remaining recent entry, try again

    parts = [p for p in (header, summary_block) if p]
    combined = "\n\n".join(parts)
    if len(combined) <= max_chars:
        return combined
    return summary_block[-max_chars:] if summary_block else "(no memory yet)"


# --- DB integration -----------------------------------------------------

async def read_memory(db, agent_id: str, llm) -> str:
    from app import models  # local import: keeps this module importable/testable without SQLAlchemy

    agent = db.get(models.Agent, agent_id)
    entries = (
        db.query(models.MemoryEntry)
        .filter(models.MemoryEntry.agent_id == agent_id)
        .order_by(models.MemoryEntry.created_at)
        .all()
    )
    if not entries:
        return "(no memory yet)"

    plan = plan_compaction(entries)

    if plan.to_summarize:
        new_summary = await llm.summarize(
            agent.memory_summary or "",
            [e.content for e in plan.to_summarize],
        )
        agent.memory_summary = new_summary
        for e in plan.to_summarize:
            e.summarized = True
        db.commit()

    return assemble_memory_context(agent.memory_summary or "", plan.recent)


async def write_memory(db, agent_id: str, content: str) -> None:
    from app import models

    db.add(models.MemoryEntry(agent_id=agent_id, content=content))
    db.commit()
