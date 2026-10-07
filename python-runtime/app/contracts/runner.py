"""C-5: the Runner and what the platform gives it. Protocols (see docs/CONTRACTS.md)."""
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Protocol

from .events import EventDraft
from .graph import AgentGraph, ToolBinding
from .memory import IntentStore, LessonStore, MemoryStore, RunHistory
from .run import RunRequest, RunResult
from .tools import CancelToken, Permission, RunWorkspace, Tool

Emit = Callable[[EventDraft], Awaitable[None]]
Clock = Callable[[], datetime]          # returns timezone-aware UTC; tests pass a fake


class ApprovalGate(Protocol):
    async def check(self, *, tool: str, permissions: set[Permission], args_preview: str,
                    span_id: str, force: bool = False, reason: str = "") -> bool: ...
    # True = go ahead, False = denied. The gate emits approval_requested / approval_resolved itself.


class ToolFactory(Protocol):
    def build(self, binding: ToolBinding) -> Tool: ...


class Runner(Protocol):
    async def run(self, req: RunRequest, *, graph: AgentGraph, emit: Emit, cancel: CancelToken,
                  approvals: ApprovalGate, workspace: RunWorkspace, tools: ToolFactory,
                  memory: MemoryStore, lessons: LessonStore, intents: IntentStore,
                  run_history: RunHistory, clock: Clock | None = None) -> RunResult: ...


__all__ = ["Emit", "Clock", "CancelToken", "ApprovalGate", "ToolFactory", "Runner"]
