"""Adapter for running legacy string-input tools through the v2 Tool contract."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.contracts.graph import ToolBinding
from app.contracts.naming import sanitize_tool_name
from app.contracts.tools import Permission, Tool as V2Tool, ToolContext, ToolError, ToolResult
from app.tools.base import Tool as LegacyTool, ToolExecutionError


class LegacyInput(BaseModel):
    """Legacy tools receive one explicit string, as documented in D-08."""
    model_config = ConfigDict(extra="forbid")

    input: str


_PERMISSION_MAP: dict[str, set[Permission]] = {
    "python": {"subprocess"},
    "http_request": {"net"},
    "web_search": {"net"},
    "file_system": {"fs_write"},
}


class LegacyToolAdapter(V2Tool):
    Input = LegacyInput

    def __init__(self, legacy: LegacyTool, binding: ToolBinding):
        self._legacy = legacy
        self.kind = binding.kind
        self.name = sanitize_tool_name(binding.name or binding.kind or legacy.name)
        self.default_description = binding.description or legacy.description
        self.permissions = set(_PERMISSION_MAP.get(binding.kind, set()))

    async def run(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        try:
            content = await self._legacy.execute(args.input, context=ctx)
        except ToolExecutionError as exc:
            raise ToolError(str(exc)) from exc
        return ToolResult(content=str(content))
