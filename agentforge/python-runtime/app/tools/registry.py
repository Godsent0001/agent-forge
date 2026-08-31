"""
Maps a persisted Tool row (kind="web_search", config={...}) to a live
Tool instance the runtime can call .execute() on. This is the seam where
a user-configured tool (from the Tool Library UI, Phase 3) becomes an
actual callable object at execution time.
"""

from __future__ import annotations

from app.tools.base import Tool
from app.tools.filesystem import FileSystemTool
from app.tools.http_request import HttpRequestTool
from app.tools.python_exec import PythonExecTool
from app.tools.web_search import WebSearchTool


def build_tool(kind: str, config: dict) -> Tool:
    if kind == "web_search":
        return WebSearchTool()
    if kind == "python":
        return PythonExecTool()
    if kind == "file_system":
        root_dir = config.get("root_dir", "./files")
        return FileSystemTool(root_dir=root_dir)
    if kind == "http_request":
        return HttpRequestTool()
    raise ValueError(f"Unknown tool kind: {kind}")
