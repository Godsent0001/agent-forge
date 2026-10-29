from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import threading

import pytest

from app.contracts.tools import ToolError
from app.core.tools.workspace_capabilities import (
    KnowledgeIngestTool,
    KnowledgeSearchTool,
    WorkspaceCapabilityToolFactory,
    WorkspaceEditTool,
    WorkspaceFilesTool,
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
async def test_workspace_knowledge_tools_and_factory(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTFORGE_DATA_DIR", str(tmp_path / "agentforge-data"))
    (tmp_path / "source.md").write_text(
        "The production system uses persistent checkpoints and durable execution plans.",
        encoding="utf-8",
    )
    ctx = SimpleNamespace(workspace=Workspace(tmp_path), execution_id="run-1", project_id="project-1", agent_id="agent-1")
    ingest = KnowledgeIngestTool()
    ingest_args = ingest.Input(path="source.md")
    result = await ingest.run(ingest_args, ctx)
    assert result.ok and "chunks_indexed" in result.content

    # A second run gets a different workspace but the same project index.
    second_workspace = tmp_path / "another-run"
    second_workspace.mkdir()
    second_ctx = SimpleNamespace(
        workspace=Workspace(second_workspace),
        execution_id="run-2",
        project_id="project-1",
        agent_id="agent-2",
    )
    search = KnowledgeSearchTool()
    found = await search.run(search.Input(query="durable execution"), second_ctx)
    assert "persistent checkpoints" in found.content

    factory = WorkspaceCapabilityToolFactory(Delegate())
    assert isinstance(factory.build(SimpleNamespace(kind="workspace_edit")), WorkspaceEditTool)
    assert factory.build(SimpleNamespace(kind="legacy_tool")) == ("delegated", "legacy_tool")


@pytest.mark.asyncio
async def test_workspace_edit_tool_uses_expected_hash(tmp_path):
    target = tmp_path / "notes.txt"
    target.write_text("one\ntwo\n", encoding="utf-8")
    ctx = SimpleNamespace(workspace=Workspace(tmp_path), execution_id="run-2", project_id="project-1", agent_id="agent-2")
    tool = WorkspaceEditTool()
    digest = __import__("hashlib").sha256(target.read_bytes()).hexdigest()
    result = await tool.run(tool.Input(
        path="notes.txt", expected_sha256=digest,
        replacements=[{"expected_text": "two", "replacement_text": "TWO"}],
    ), ctx)
    assert result.ok and target.read_text(encoding="utf-8") == "one\nTWO\n"



def test_knowledge_index_persists_and_uses_chunk_embeddings(tmp_path):
    from app.core.knowledge import KnowledgeIndex, extract_document

    index_path = tmp_path / "knowledge.sqlite3"
    index = KnowledgeIndex(index_path)
    document = extract_document(
        "orbit.md",
        b"An orbital vehicle circles a planet and transmits telemetry to a ground station.",
    )
    count = index.ingest(document, embedding_fn=lambda texts: [[1.0, 0.0] for _ in texts])
    assert count == 1
    assert index.last_ingest_embedded is True

    # A fresh index instance proves vectors were persisted rather than held only in memory.
    reopened = KnowledgeIndex(index_path)
    hits = reopened.search("celestial object", query_embedding=[1.0, 0.0], limit=3)
    assert hits
    assert hits[0].chunk.source_name == "orbit.md"
    assert hits[0].semantic_score > 0


@pytest.mark.asyncio
async def test_workspace_files_tool_creates_reads_lists_and_overwrites_in_workspace(tmp_path):
    ctx = SimpleNamespace(workspace=Workspace(tmp_path), execution_id="file-run", project_id="project-1", agent_id="agent-1")
    tool = WorkspaceFilesTool()

    made_dir = await tool.run(tool.Input(action="mkdir", path="calculator"), ctx)
    assert '"created": true' in made_dir.content
    created = await tool.run(tool.Input(action="write", path="calculator/main.py", content="print(2 + 2)"), ctx)
    assert '"written": true' in created.content
    assert (tmp_path / "calculator" / "main.py").read_text(encoding="utf-8") == "print(2 + 2)"

    with pytest.raises(ToolError, match="File already exists"):
        await tool.run(tool.Input(action="write", path="calculator/main.py", content="print(0)"), ctx)

    read = await tool.run(tool.Input(action="read", path="calculator/main.py"), ctx)
    assert "print(2 + 2)" in read.content
    listing = await tool.run(tool.Input(action="list", path="calculator"), ctx)
    assert '"name": "main.py"' in listing.content


@pytest.mark.asyncio
async def test_workspace_files_tool_rejects_path_traversal_and_requires_delete_approval(tmp_path):
    ctx = SimpleNamespace(workspace=Workspace(tmp_path), execution_id="file-run", project_id="project-1", agent_id="agent-1")
    tool = WorkspaceFilesTool()
    with pytest.raises(ToolError, match="path escapes workspace|outside the project workspace"):
        await tool.run(tool.Input(action="read", path="../outside.txt"), ctx)
    assert tool.requires_approval({"action": "delete"})
    assert not tool.requires_approval({"action": "read"})


@pytest.mark.asyncio
async def test_knowledge_search_skips_embedding_model_when_index_has_no_vectors(tmp_path, monkeypatch):
    from app.core import knowledge as knowledge_module
    from app.core.tools import workspace_capabilities
    from app.infra.paths import project_dir

    monkeypatch.setenv("AGENTFORGE_DATA_DIR", str(tmp_path / "agentforge-data"))
    ctx = SimpleNamespace(
        workspace=Workspace(tmp_path), execution_id="lexical-only-run",
        project_id="lexical-only-project", agent_id="agent-1",
    )
    index = knowledge_module.KnowledgeIndex(
        project_dir(ctx.project_id) / ".agentforge" / "knowledge.sqlite3"
    )
    document = knowledge_module.extract_document(
        "brief.md", b"The workspace stores durable execution checkpoints and task plans."
    )
    index.ingest(document)

    def unexpected_embedding(*args, **kwargs):
        raise AssertionError("embedding model should not load for a lexical-only index")

    monkeypatch.setattr(workspace_capabilities, "embed_text", unexpected_embedding)
    result = await workspace_capabilities.KnowledgeSearchTool().run(
        workspace_capabilities.KnowledgeSearchInput(query="execution checkpoints"), ctx
    )
    assert '"retrieval_mode": "lexical_fallback"' in result.content
    assert "durable execution checkpoints" in result.content


@pytest.mark.asyncio
async def test_knowledge_search_runs_embedding_inference_off_event_loop(tmp_path, monkeypatch):
    from app.core import knowledge as knowledge_module
    from app.core.tools import workspace_capabilities
    from app.infra.paths import project_dir

    monkeypatch.setenv("AGENTFORGE_DATA_DIR", str(tmp_path / "agentforge-data"))
    ctx = SimpleNamespace(
        workspace=Workspace(tmp_path), execution_id="threaded-search-run",
        project_id="threaded-search-project", agent_id="agent-1",
    )
    index = knowledge_module.KnowledgeIndex(
        project_dir(ctx.project_id) / ".agentforge" / "knowledge.sqlite3"
    )
    document = knowledge_module.extract_document(
        "orbit.md", b"An orbital vehicle transmits telemetry to a ground station."
    )
    index.ingest(document, embedding_fn=lambda texts: [[1.0, 0.0] for _ in texts])

    main_thread = threading.current_thread()
    called_off_loop = []

    def fake_embed(_query, _model_id):
        called_off_loop.append(threading.current_thread() is not main_thread)
        return [1.0, 0.0]

    monkeypatch.setattr(workspace_capabilities, "embed_text", fake_embed)
    result = await workspace_capabilities.KnowledgeSearchTool().run(
        workspace_capabilities.KnowledgeSearchInput(query="space telemetry"), ctx
    )
    assert called_off_loop == [True]
    assert "hybrid_vector_lexical" in result.content
