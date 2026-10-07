from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.contracts.graph import ToolBinding
from app.contracts.tools import ArtifactRef, Tool as V2Tool, ToolContext, ToolError, ToolResult
from app.tools.registry import build_tool


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
        self.default_description = binding.description or binding.kind
        self._legacy = build_tool(binding.kind, binding.config or {})

    @property
    def name(self) -> str:
        return self.kind

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
        self.root = Path(tempfile.mkdtemp(prefix=f"agentforge-{execution_id}-"))

    def resolve(self, rel: str) -> Path:
        candidate = (self.root / rel).resolve()
        if self.root not in candidate.parents and candidate != self.root:
            raise ToolError(f"Path escapes run workspace: {rel}")
        return candidate

    def new_path(self, name: str) -> Path:
        return self.resolve(name)

    def relative(self, p: Path) -> str:
        return str(p.resolve().relative_to(self.root))

    def write_result(self, tool_call_id: str, content: str) -> ArtifactRef:
        result_dir = self.root / ".results"
        result_dir.mkdir(parents=True, exist_ok=True)
        path = result_dir / f"{tool_call_id}.txt"
        path.write_text(content, encoding="utf-8")
        return ArtifactRef(path=self.relative(path), mime="text/plain")

    def cleanup(self) -> None:
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)


class LegacyToolFactory:
    def build(self, binding: ToolBinding) -> V2Tool:
        return LegacyToolAdapter(binding)


class NullApprovals:
    async def check(self, **kwargs: Any) -> bool:
        return True
