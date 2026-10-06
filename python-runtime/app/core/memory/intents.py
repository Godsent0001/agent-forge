"""Standing intents tools for creating, listing, and cancelling reminders."""
import uuid
from datetime import datetime, timezone
from typing import Any, ClassVar, Literal
from pydantic import BaseModel, Field

from app.contracts.memory import Intent, IntentStore
from app.contracts.tools import Tool, ToolError, ToolResult


class IntentCreateInput(BaseModel):
    text: str = Field(description="The reminder text (max 300 characters)")
    when: str = Field(description="'next_run' or ISO datetime string in UTC")
    evidence: str = Field(description="Verbatim user quote requesting this reminder")
    repeat: Literal["none", "daily", "weekly"] = Field(default="none", description="Repeat schedule")


class IntentCreateTool(Tool):
    """Tool to create a reminder (standing intent) for the user."""

    kind: ClassVar[str] = "intent_create"
    default_description: ClassVar[str] = "Create a reminder for the user."
    Input: ClassVar[type[BaseModel]] = IntentCreateInput

    def __init__(self, store: IntentStore):
        self.store = store

    async def run(self, args: IntentCreateInput, ctx: Any) -> ToolResult:
        if not args.evidence or not args.evidence.strip():
            raise ToolError("Missing verbatim user quote in 'evidence' parameter.")

        if len(args.text) > 300:
            raise ToolError("Reminder text exceeds maximum limit of 300 characters.")

        trigger = "next_run" if args.when == "next_run" else "at_time"
        due_at = None
        if trigger == "at_time":
            try:
                due_at = datetime.fromisoformat(args.when)
            except Exception:
                raise ToolError("Invalid datetime format for 'when'. Expected ISO format.")

        now = datetime.now(timezone.utc)
        intent = Intent(
            id=str(uuid.uuid4()),
            agent_id=getattr(ctx, "agent_id", "root"),
            text=args.text.strip(),
            trigger=trigger,
            due_at=due_at,
            repeat=args.repeat,
            mode="remind",
            status="active",
            evidence=args.evidence.strip(),
            source_execution_id=getattr(ctx, "execution_id", None),
            created_at=now,
        )

        await self.store.create(intent)
        return ToolResult(ok=True, content=f"Created reminder '{intent.text}' (id: {intent.id}).")


class IntentListInput(BaseModel):
    pass


class IntentListTool(Tool):
    """Read-only tool to list active reminders."""

    kind: ClassVar[str] = "intent_list"
    default_description: ClassVar[str] = "List active reminders for the current agent."
    Input: ClassVar[type[BaseModel]] = IntentListInput

    def __init__(self, store: IntentStore):
        self.store = store

    async def run(self, args: IntentListInput, ctx: Any) -> ToolResult:
        items = await self.store.list(agent_id=getattr(ctx, "agent_id", "root"), status="active")
        if not items:
            return ToolResult(ok=True, content="No active reminders.")

        lines = [f"- [{i.id}] {i.text} (trigger: {i.trigger}, repeat: {i.repeat})" for i in items]
        return ToolResult(ok=True, content="\n".join(lines))


class IntentCancelInput(BaseModel):
    intent_id: str = Field(description="ID of the reminder to cancel")


class IntentCancelTool(Tool):
    """Tool to cancel an active reminder."""

    kind: ClassVar[str] = "intent_cancel"
    default_description: ClassVar[str] = "Cancel an active reminder."
    Input: ClassVar[type[BaseModel]] = IntentCancelInput

    def __init__(self, store: IntentStore):
        self.store = store

    async def run(self, args: IntentCancelInput, ctx: Any) -> ToolResult:
        await self.store.cancel(args.intent_id)
        return ToolResult(ok=True, content=f"Cancelled reminder {args.intent_id}.")
