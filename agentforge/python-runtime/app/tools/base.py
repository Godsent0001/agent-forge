"""
The universal Tool interface. Every real tool (this file's implementations)
and every AgentTool (Phase 6) implement this exact interface — the runtime
never special-cases either one.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ToolExecutionError(RuntimeError):
    """Raised when a tool fails in an expected, reportable way (bad input,
    sandboxed subprocess non-zero exit, network failure, etc.) — as
    opposed to a bug in the runtime itself."""


class Tool(ABC):
    name: str
    description: str

    @abstractmethod
    async def execute(self, input: str, *, context: Any) -> str:
        """
        `context` is an ExecutionContext (see app/runtime/context.py, Phase 6).
        Kept as `Any` here to avoid a circular import between tools and
        runtime — both depend on this interface, not on each other.
        """
        ...
