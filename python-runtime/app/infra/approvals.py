"""Human-in-the-loop approval gate for side-effecting tools."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.contracts.events import EventDraft
from app.contracts.tools import Permission

# Known tools default to Allow for frictionless execution. Unknown tool types
# default to Ask so newly added tools cannot silently bypass approval.
DEFAULT_POLICIES = {
    "python": "allow",
    "shell": "allow",
    "http_request": "allow",
    "browser": "allow",
    "web_search": "allow",
    "video_source": "allow",
    "video_transcript": "allow",
    "clip_finder": "allow",
    "clip_extractor": "allow",
    "file_system": "allow",
    "scene_template_manager": "allow",
    "render_queue": "allow",
    "project_manager": "allow",
    "asset_cache_store": "allow",
    "production_config": "allow",
    "cache_engine": "allow",
}
APPROVAL_TIMEOUT_SECONDS = 300


@dataclass
class PendingApproval:
    approval_id: str
    execution_id: str
    tool: str
    kind: str
    future: asyncio.Future[str]
    gate: "ApprovalGateImpl"


PENDING: dict[str, PendingApproval] = {}


class ApprovalGateImpl:
    def __init__(self, *, execution_id: str, settings: dict[str, Any], emit, tool_kinds: dict[str, str] | None = None, timeout_seconds: int = APPROVAL_TIMEOUT_SECONDS):
        self.execution_id = execution_id
        self.settings = settings or {}
        self.emit = emit
        self.tool_kinds = tool_kinds or {}
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.allowed_for_run: set[tuple[str, str]] = set()

    def _kind_for(self, tool: str) -> str:
        if tool in self.tool_kinds:
            return self.tool_kinds[tool]
        # Only known built-in tool names inherit their own default policy.
        # Unknown names remain unknown even if their permissions resemble a
        # built-in tool, so they fall back to Ask rather than silently Allow.
        return tool

    def _policy_for(self, kind: str, permissions: set[Permission]) -> str:
        configured = self.settings.get("tool_policy", {})
        policy = configured.get(kind) if isinstance(configured, dict) else None
        if policy not in {"allow", "ask", "deny"}:
            policy = DEFAULT_POLICIES.get(kind, "ask")
        return policy

    async def check(self, *, tool: str, permissions: set[Permission], args_preview: str, span_id: str, force: bool = False, reason: str = "") -> bool:
        kind = self._kind_for(tool)
        if (self.execution_id, tool) in self.allowed_for_run:
            return True

        policy = "ask" if force else self._policy_for(kind, permissions)
        if policy == "deny":
            return False
        if policy == "allow":
            return True

        loop = asyncio.get_running_loop()
        approval_id = str(uuid4())
        future: asyncio.Future[str] = loop.create_future()
        pending = PendingApproval(approval_id, self.execution_id, tool, kind, future, self)
        PENDING[approval_id] = pending
        decision = "deny"
        timed_out = False
        cancelled = False
        try:
            await self.emit(EventDraft(
                type="approval_requested",
                span_id=span_id,
                kind="tool_call",
                name=tool[:2000],
                data={
                    "approval_id": approval_id,
                    "tool": tool[:2000],
                    "tool_kind": kind[:200],
                    "permissions": sorted(permissions),
                    "args_preview": args_preview[:2000],
                    "reason": (reason or f"Tool policy for {kind} requires approval")[:2000],
                    "timeout_seconds": self.timeout_seconds,
                },
            ))
            try:
                decision = await asyncio.wait_for(future, timeout=self.timeout_seconds)
            except asyncio.TimeoutError:
                decision = "deny"
                timed_out = True
            except asyncio.CancelledError:
                decision = "deny"
                cancelled = True
        finally:
            PENDING.pop(approval_id, None)
            if not future.done():
                future.cancel()
            try:
                await asyncio.shield(self.emit(EventDraft(
                    type="approval_resolved",
                    span_id=span_id,
                    kind="tool_call",
                    name=tool[:2000],
                    data={
                        "approval_id": approval_id,
                        "decision": decision,
                        "allowed": decision in {"allow_once", "allow_run"},
                        "timed_out": timed_out,
                        "cancelled": cancelled,
                    },
                )))
            except Exception:
                pass

        if cancelled:
            raise asyncio.CancelledError
        if decision == "allow_run":
            self.allowed_for_run.add((self.execution_id, tool))
        return decision in {"allow_once", "allow_run"}


def resolve_approval(*, execution_id: str, approval_id: str, decision: str) -> bool:
    """Resolve a live request once; return False when it is missing or belongs to another run."""
    if decision not in {"allow_once", "allow_run", "deny"}:
        raise ValueError("Decision must be allow_once, allow_run, or deny")
    pending = PENDING.get(approval_id)
    if not pending or pending.execution_id != execution_id or pending.future.done():
        return False
    if decision == "allow_run":
        pending.gate.allowed_for_run.add((execution_id, pending.tool))
    pending.future.set_result(decision)
    return True
