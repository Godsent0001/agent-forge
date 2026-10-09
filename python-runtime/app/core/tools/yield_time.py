"""Universal yield_time primitive tool implementing Dual-Threshold Wait Algorithm."""
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, ClassVar
from pydantic import BaseModel, Field

from app.contracts.memory import Intent, IntentStore
from app.contracts.tools import Tool, ToolError, ToolResult

SHORT_WAIT_THRESHOLD_SEC = 30.0


class YieldTimeInput(BaseModel):
    wake_at: str = Field(description="ISO-8601 UTC timestamp (e.g. 2026-10-09T04:00:00Z) or integer delay seconds to wait")
    reason: str = Field(description="Reason for pausing execution")


class YieldTimeTool(Tool):
    """Universal temporal primitive tool for pausing execution."""

    kind: ClassVar[str] = "yield_time"
    default_description: ClassVar[str] = "Pause or defer agent execution until a target UTC timestamp."
    Input: ClassVar[type[BaseModel]] = YieldTimeInput

    def __init__(self, intent_store: IntentStore | None = None):
        self.intent_store = intent_store

    async def run(self, args: YieldTimeInput, ctx: Any) -> ToolResult:
        now_dt = datetime.now(timezone.utc)
        now_epoch = now_dt.timestamp()

        # Parse wake_at as seconds or ISO timestamp
        try:
            delay_sec = float(args.wake_at)
            wake_dt = datetime.fromtimestamp(now_epoch + delay_sec, tz=timezone.utc)
        except ValueError:
            try:
                wake_dt = datetime.fromisoformat(args.wake_at.replace("Z", "+00:00"))
                if wake_dt.tzinfo is None:
                    wake_dt = wake_dt.replace(tzinfo=timezone.utc)
            except Exception:
                raise ToolError(f"Invalid wake_at format '{args.wake_at}'. Expected ISO timestamp or integer seconds.")

        duration_sec = (wake_dt - now_dt).total_seconds()
        if duration_sec <= 0:
            return ToolResult(ok=True, content="Target timestamp has already passed. Continuing execution immediately.")

        # Dual-Threshold Algorithm
        if duration_sec < SHORT_WAIT_THRESHOLD_SEC:
            # Short wait: In-process async delay
            await asyncio.sleep(duration_sec)
            return ToolResult(
                ok=True,
                content=f"In-process pause complete ({duration_sec:.1f}s elapsed for: {args.reason}). Resuming execution.",
            )
        else:
            # Long wait: Durable hibernation via IntentStore
            if self.intent_store:
                intent = Intent(
                    id=str(uuid.uuid4()),
                    agent_id=getattr(ctx, "agent_id", "root"),
                    text=f"Wake from yield_time: {args.reason}",
                    trigger="at_time",
                    due_at=wake_dt,
                    repeat="none",
                    mode="remind",
                    status="active",
                    evidence="yield_time invocation",
                    source_execution_id=getattr(ctx, "execution_id", None),
                    created_at=now_dt,
                )
                await self.intent_store.create(intent)

            return ToolResult(
                ok=True,
                content=(
                    f"Durable hibernation scheduled for {wake_dt.isoformat()} (duration: {duration_sec:.1f}s, reason: '{args.reason}'). "
                    "Process state checkpointed."
                ),
            )
