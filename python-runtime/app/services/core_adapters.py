from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.contracts.graph import ToolBinding
from app.contracts.naming import sanitize_tool_name
from app.contracts.tools import ArtifactRef, ToolContext, ToolError, ToolResult
from app.contracts.tools import Tool as V2Tool
from app.tools.registry import build_tool
from app.infra.workspace import RunWorkspace as SafeRunWorkspace


class LegacyToolInput(BaseModel):
    model_config = ConfigDict(extra="allow")


class LegacyExecutionContext:
    def __init__(self, execution_id: str, workspace: "Workspace", cancel: Any):
        self.execution_id = execution_id
        self.workspace = workspace
        self.cancel = cancel


class LegacyToolAdapter(V2Tool):
    Input = LegacyToolInput
    permissions = set()

    def __init__(self, binding: ToolBinding):
        self.kind = binding.kind
        self._name = sanitize_tool_name(binding.name or binding.kind)
        self.default_description = binding.description or binding.kind
        self._legacy = build_tool(binding.kind, binding.config or {})

    @property
    def name(self) -> str:
        return self._name

    async def run(self, args: LegacyToolInput, ctx: ToolContext) -> ToolResult:
        payload = args.model_dump(exclude_none=True)
        if self.kind == "web_search":
            raw = str(payload.get("query", ""))
        elif self.kind == "python":
            raw = str(payload.get("code", payload.get("input", "")))
        elif self.kind == "http_request":
            method = str(payload.get("method", "GET")).upper()
            url = str(payload.get("url", ""))
            body = payload.get("body")
            raw = f"{method} {url}" + (f"::{json.dumps(body)}" if body is not None else "")
        elif self.kind == "file_system":
            op = str(payload.get("op", "list"))
            path = str(payload.get("path", "."))
            if op == "write":
                raw = f"write:{path}::{payload.get('content', '')}"
            else:
                raw = f"{op}:{path}"
        elif len(payload) == 1 and "input" in payload:
            raw = str(payload["input"])
        else:
            raw = json.dumps(payload, ensure_ascii=False)

        try:
            content = await self._legacy.execute(
                raw,
                context=LegacyExecutionContext(ctx.execution_id, ctx.workspace, ctx.cancel),
            )
        except Exception as exc:
            message = getattr(exc, "message", None) or str(exc)
            raise ToolError(message) from exc

        return ToolResult(ok=True, content=content)


class Workspace:
    def __init__(self, execution_id: str):
        self._workspace = SafeRunWorkspace(execution_id)
        self.root = self._workspace.root

    def resolve(self, rel: str) -> Path:
        return self._workspace.resolve(rel)

    def new_path(self, name: str) -> Path:
        return self._workspace.new_path(name)

    def relative(self, p: Path) -> str:
        return self._workspace.relative(p)

    def write_result(self, tool_call_id: str, content: str) -> ArtifactRef:
        return self._workspace.write_result(tool_call_id, content)

    def cleanup(self) -> None:
        # Run artifacts must remain available to the UI after execution.
        return None


class LegacyToolFactory:
    def build(self, binding: ToolBinding) -> V2Tool:
        return LegacyToolAdapter(binding)


class NullApprovals:
    async def check(self, **kwargs: Any) -> bool:
        return True
