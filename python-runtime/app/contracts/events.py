from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


EventType = Literal[
    "execution_started",
    "span_started",
    "span_ended",
    "approval_requested",
    "approval_resolved",
    "execution_ended",
]
SpanKind = Literal["agent", "llm_call", "tool_call"]
SpanStatus = Literal["ok", "error", "cancelled"]


class EventDraft(BaseModel):
    type: EventType
    span_id: str | None = None
    parent_span_id: str | None = None
    kind: SpanKind | None = None
    name: str | None = None
    status: SpanStatus | None = None
    data: dict = Field(default_factory=dict)


class RunEvent(EventDraft):
    execution_id: str
    seq: int
    ts: datetime
