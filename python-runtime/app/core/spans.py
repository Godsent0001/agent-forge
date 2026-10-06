"""Span context manager and event tracing utilities for AgentForge Core."""
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from app.contracts.events import EventDraft, SpanKind, SpanStatus
from app.contracts.runner import Emit


@asynccontextmanager
async def span(
    emit: Emit,
    kind: SpanKind,
    name: str | None = None,
    parent_span_id: str | None = None,
    data: dict[str, Any] | None = None,
) -> AsyncGenerator[str, None]:
    """Async context manager for span lifecycle management. Ensures span_ended is always emitted."""
    span_id = str(uuid.uuid4())
    start_data = dict(data or {})

    await emit(
        EventDraft(
            type="span_started",
            span_id=span_id,
            parent_span_id=parent_span_id,
            kind=kind,
            name=name,
            data=start_data,
        )
    )

    status: SpanStatus = "ok"
    end_data: dict[str, Any] = {}
    try:
        yield span_id
    except Exception as exc:
        status = "error"
        end_data["error"] = str(exc)
        raise
    finally:
        await emit(
            EventDraft(
                type="span_ended",
                span_id=span_id,
                parent_span_id=parent_span_id,
                kind=kind,
                name=name,
                status=status,
                data=end_data,
            )
        )
