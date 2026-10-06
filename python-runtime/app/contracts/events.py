"""C-2: events (the trace). Pure data (see docs/CONTRACTS.md)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

EventType = Literal["execution_started", "span_started", "span_ended",
                    "approval_requested", "approval_resolved", "execution_ended"]
SpanKind = Literal["agent", "llm_call", "tool_call"]
SpanStatus = Literal["ok", "error", "cancelled"]

# R5 limits
EVENT_STRING_LIMIT = 2_000
EVENT_DATA_LIMIT_BYTES = 8 * 1024

# `name` values the core gives to llm_call spans that are not a normal agent turn.
WELL_KNOWN_LLM_CALL_NAMES = ("memory_extract", "compaction", "trim_summary", "embed")


class EventDraft(BaseModel):
    """What the Runner passes to emit(). The emitter fills execution_id, seq, ts."""
    type: EventType
    span_id: str | None = None
    parent_span_id: str | None = None
    kind: SpanKind | None = None
    name: str | None = None
    status: SpanStatus | None = None        # set on span_ended
    data: dict = {}


class RunEvent(EventDraft):
    execution_id: str
    seq: int                                # 1, 2, 3... no gaps, per execution
    ts: datetime                            # UTC
