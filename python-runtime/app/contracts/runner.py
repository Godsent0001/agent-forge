from asyncio import CancelledError
from collections.abc import Awaitable, Callable
from typing import Protocol

from .events import EventDraft
from .graph import AgentGraph
from .run import RunRequest, RunResult
from .tools import Permission, RunWorkspace, Tool, ToolBinding


Emit = Callable[[EventDraft], Awaitable[None]]


class CancelToken(Protocol):
    @property
    def cancelled(self) -> bool: ...

    def raise_if_cancelled(self) -> None: ...


class ApprovalGate(Protocol):
    async def check(
        self,
        *,
        tool: str,
        permissions: set[Permission],
        args_preview: str,
        span_id: str,
        force: bool = False,
        reason: str = "",
    ) -> bool: ...


class ToolFactory(Protocol):
    def build(self, binding: ToolBinding) -> Tool: ...


class MemoryStore(Protocol):
    async def recall(self, agent_id: str, query: str, budget_tokens: int) -> list[object]: ...
    async def add(self, agent_id: str, items: list[object]) -> None: ...
    async def summary(self, agent_id: str) -> str: ...
    async def set_summary(self, agent_id: str, text: str) -> None: ...


class Runner(Protocol):
    async def run(
        self,
        req: RunRequest,
        *,
        graph: AgentGraph,
        emit: Emit,
        cancel: CancelToken,
        approvals: ApprovalGate,
        memory: MemoryStore,
        workspace: RunWorkspace,
        tools: ToolFactory,
    ) -> RunResult: ...
