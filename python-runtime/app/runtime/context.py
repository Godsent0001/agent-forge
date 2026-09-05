"""
Production version of the ExecutionContext proven in the Phase 0.5 spike.
Same guards (recursion depth, cycle detection), now emitting events through
a sink that Phase 7 wires to both SQLite persistence and a WebSocket
broadcast, instead of print().
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

MAX_RECURSION_DEPTH = 8


class RecursionLimitError(RuntimeError):
    pass


class CycleDetectedError(RuntimeError):
    pass


@dataclass
class ExecutionEvent:
    type: str
    agent_name: str | None = None
    tool_name: str | None = None
    depth: int = 0
    data: dict[str, Any] = field(default_factory=dict)


EventSink = Callable[[ExecutionEvent], Awaitable[None]]


async def _noop_sink(event: ExecutionEvent) -> None:
    return None


@dataclass
class ExecutionContext:
    execution_id: str
    depth: int = 0
    visited_agent_ids: tuple[str, ...] = ()
    sink: EventSink = _noop_sink

    async def emit(self, type: str, *, agent_name: str | None = None,
                    tool_name: str | None = None, data: dict[str, Any] | None = None) -> None:
        await self.sink(ExecutionEvent(
            type=type, agent_name=agent_name, tool_name=tool_name,
            depth=self.depth, data=data or {},
        ))

    def descend(self, agent_id: str) -> "ExecutionContext":
        if self.depth + 1 > MAX_RECURSION_DEPTH:
            raise RecursionLimitError(
                f"Max recursion depth ({MAX_RECURSION_DEPTH}) exceeded at agent {agent_id}"
            )
        if agent_id in self.visited_agent_ids:
            raise CycleDetectedError(
                f"Cycle detected: agent {agent_id} already active in this execution "
                f"(chain: {' -> '.join(self.visited_agent_ids)} -> {agent_id})"
            )
        return ExecutionContext(
            execution_id=self.execution_id,
            depth=self.depth + 1,
            visited_agent_ids=self.visited_agent_ids + (agent_id,),
            sink=self.sink,
        )
