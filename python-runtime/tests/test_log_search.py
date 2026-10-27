from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.tools.log_search import LogSearchTool


class Workspace:
    def __init__(self, root):
        self.root = root

    def resolve(self, relative):
        from pathlib import Path
        candidate = (self.root / relative).resolve()
        if not candidate.is_relative_to(self.root.resolve()):
            raise ValueError("path escapes workspace")
        return candidate


@pytest.mark.asyncio
async def test_log_search_returns_relevant_excerpt_and_line_range(tmp_path):
    path = tmp_path / ".results" / "build.txt"
    path.parent.mkdir()
    path.write_text(
        "Starting build\nCompiling assets\nModuleNotFoundError: missing package xyz\nBuild failed",
        encoding="utf-8",
    )
    context = SimpleNamespace(workspace=Workspace(tmp_path))
    tool = LogSearchTool(embedding_fn=lambda _: [])
    result = await tool.execute(".results/build.txt::ModuleNotFoundError missing package", context=context)

    assert "Search method: keyword" in result
    assert "ModuleNotFoundError" in result
    assert "lines" in result


@pytest.mark.asyncio
async def test_log_search_rejects_path_traversal(tmp_path):
    context = SimpleNamespace(workspace=Workspace(tmp_path))
    with pytest.raises(Exception, match="invalid workspace log path"):
        await LogSearchTool(embedding_fn=lambda _: []).execute("../outside.txt::error", context=context)
