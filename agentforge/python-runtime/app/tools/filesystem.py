"""
File System tool. Scoped to a single root directory (the project's own
`files/` folder) so an agent can never read/write outside its project,
regardless of what path it's given.

Input format (kept simple/scriptable for the LLM to produce):
    "read:<relative_path>"
    "write:<relative_path>::<content>"
    "list:<relative_path>"
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.tools.base import Tool, ToolExecutionError


class FileSystemTool(Tool):
    name = "file_system"
    description = "Read, write, or list files within the project's files directory."

    def __init__(self, root_dir: str):
        self._root = Path(root_dir).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, relative_path: str) -> Path:
        candidate = (self._root / relative_path).resolve()
        # The core guard: reject any path that escapes the root, e.g. via "../../".
        if self._root not in candidate.parents and candidate != self._root:
            raise ToolExecutionError(f"Path '{relative_path}' escapes the allowed root directory")
        return candidate

    async def execute(self, input: str, *, context: Any) -> str:
        if input.startswith("read:"):
            path = self._resolve(input[len("read:"):])
            if not path.is_file():
                raise ToolExecutionError(f"No such file: {path.relative_to(self._root)}")
            return path.read_text(errors="replace")

        if input.startswith("write:"):
            rest = input[len("write:"):]
            if "::" not in rest:
                raise ToolExecutionError("write: requires '<path>::<content>'")
            rel_path, content = rest.split("::", 1)
            path = self._resolve(rel_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            return f"Wrote {len(content)} bytes to {rel_path}"

        if input.startswith("list:"):
            rel_path = input[len("list:"):] or "."
            path = self._resolve(rel_path)
            if not path.is_dir():
                raise ToolExecutionError(f"No such directory: {rel_path}")
            return "\n".join(sorted(p.name for p in path.iterdir()))

        raise ToolExecutionError("Input must start with 'read:', 'write:', or 'list:'")
