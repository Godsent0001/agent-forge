"""Workspace-scoped file access for a single execution."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.tools.base import Tool, ToolExecutionError


class FileSystemTool(Tool):
    name = "file_system"
    description = "Read, write, or list files within the current run workspace."

    def __init__(self, root_dir: str):
        # Legacy-only fallback. v2 contexts always choose the run workspace below.
        self._root = Path(root_dir).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, relative_path: str, root: Path) -> Path:
        raw = relative_path
        if not raw or raw.strip() == "":
            raise ToolExecutionError("A relative file path is required")
        if raw.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", raw):
            raise ToolExecutionError("Absolute file paths are not allowed")
        normalized = raw.replace("\\", "/")
        if any(part == ".." for part in normalized.split("/")):
            raise ToolExecutionError("Parent-directory traversal is not allowed")
        candidate = (root / normalized).resolve()
        resolved_root = root.resolve()
        if not candidate.is_relative_to(resolved_root):
            raise ToolExecutionError("Path escapes the allowed workspace")
        return candidate

    def _root_for(self, context: Any) -> Path:
        workspace = getattr(context, "workspace", None)
        if workspace is not None and hasattr(workspace, "resolve"):
            return workspace.resolve("files")
        return self._root

    async def execute(self, input: str, *, context: Any) -> str:
        root = self._root_for(context)
        root.mkdir(parents=True, exist_ok=True)
        if input.startswith("read:"):
            path = self._resolve(input[len("read:"):], root)
            if not path.is_file():
                raise ToolExecutionError("File not found in workspace")
            return path.read_text(encoding="utf-8", errors="replace")

        if input.startswith("write:"):
            rest = input[len("write:"): ]
            if "::" not in rest:
                raise ToolExecutionError("write: requires '<path>::<content>'")
            rel_path, content = rest.split("::", 1)
            path = self._resolve(rel_path, root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return f"Wrote {len(content.encode('utf-8'))} bytes to {rel_path}"

        if input.startswith("list:"):
            rel_path = input[len("list:"):] or "."
            path = self._resolve(rel_path, root)
            if not path.is_dir():
                raise ToolExecutionError("Directory not found in workspace")
            return "\n".join(sorted(p.name for p in path.iterdir()))

        raise ToolExecutionError("Input must start with 'read:', 'write:', or 'list:'")
