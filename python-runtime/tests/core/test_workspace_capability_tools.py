from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.tools.workspace_capabilities import (
    KnowledgeIngestTool, KnowledgeSearchTool, WorkspaceCapabilityToolFactory, WorkspaceEditTool,
)


class Workspace:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def resolve(self, relative: str) -> Path:
        path = Path(relative)
        if path.is_absolute():
            raise ValueError("absolute paths are forbidden")
        resolved = (self.root / path).resolve()
        if self.root not in resolved.parents:
            raise ValueError("path escapes workspace")
        return resolved

    def relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()


class Delegate:
    def build(self, binding):
        return ("delegated", binding.kind)


@pytest.mark.asyncio
async def test_workspace_knowledge_tools_and_factory(tmp_path):
    (tmp_path / "source.md").write_text(
        "The production system uses persistent checkpoints and durable execution plans.",
        encoding="utf-8",
    )
    ctx = SimpleNamespace(workspace=Workspace(tmp_path), execution_id="run-1", agent_id="agent-1")
    ingest = KnowledgeIngestTool()
    ingest_args = ingest.Input(path="source.md")
    result = await ingest.run(ingest_args, ctx)
    assert result.ok and "chunks_indexed" in result.content

    search = KnowledgeSearchTool()
    found = await search.run(search.Input(query="durable execution"), ctx)
    assert "persistent checkpoints" in found.content

    factory = WorkspaceCapabilityToolFactory(Delegate())
    assert isinstance(factory.build(SimpleNamespace(kind="workspace_edit")), WorkspaceEditTool)
    assert factory.build(SimpleNamespace(kind="legacy_tool")) == ("delegated", "legacy_tool")


@pytest.mark.asyncio
async def test_workspace_edit_tool_uses_expected_hash(tmp_path):
    target = tmp_path / "notes.txt"
    target.write_text("one\ntwo\n", encoding="utf-8")
    ctx = SimpleNamespace(workspace=Workspace(tmp_path), execution_id="run-2", agent_id="agent-2")
    tool = WorkspaceEditTool()
    digest = __import__("hashlib").sha256(target.read_bytes()).hexdigest()
    result = await tool.run(tool.Input(
        path="notes.txt", expected_sha256=digest,
        replacements=[{"expected_text": "two", "replacement_text": "TWO"}],
    ), ctx)
    assert result.ok and target.read_text(encoding="utf-8") == "one\nTWO\n"
