"""Built-in workspace tools that expose shared knowledge and safe-editing services."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.contracts.tools import Permission, Tool, ToolContext, ToolError, ToolResult
from app.core.knowledge import KnowledgeIndex, extract_document
from app.core.safe_editing import EditConflict, EditError, SafeWorkspaceEditor, TextReplacement


class KnowledgeIngestInput(BaseModel):
    path: str = Field(min_length=1, max_length=1000, description="Workspace-relative source file path")
    media_type: str | None = None


class KnowledgeSearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=6, ge=1, le=20)


class ReplacementInput(BaseModel):
    expected_text: str = Field(min_length=1)
    replacement_text: str
    expected_count: int = Field(default=1, ge=1, le=10000)


class WorkspaceEditInput(BaseModel):
    path: str = Field(min_length=1, max_length=1000)
    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    replacements: list[ReplacementInput] = Field(min_length=1, max_length=100)
    reason: str = Field(default="targeted edit", max_length=2000)


def _index(ctx: ToolContext) -> KnowledgeIndex:
    return KnowledgeIndex(Path(ctx.workspace.root) / ".agentforge" / "knowledge.sqlite3")


class KnowledgeIngestTool(Tool):
    kind = "knowledge_ingest"
    default_description = (
        "Index a workspace file for later retrieval. Supports text, Markdown, code, HTML, JSON, CSV, "
        "and optional PDF/DOCX extractors. This indexes extracted text; it does not modify the source."
    )
    Input = KnowledgeIngestInput
    permissions: set[Permission] = set()

    async def run(self, args: KnowledgeIngestInput, ctx: ToolContext) -> ToolResult:
        try:
            path = ctx.workspace.resolve(args.path)
            if not path.is_file():
                raise ToolError(f"Source file does not exist: {args.path}")
            if path.stat().st_size > 50 * 1024 * 1024:
                raise ToolError("Source file exceeds the 50 MiB ingestion limit.")
            document = extract_document(
                path.name, path.read_bytes(), media_type=args.media_type,
                metadata={"workspace_path": ctx.workspace.relative(path), "execution_id": ctx.execution_id},
            )
            count = _index(ctx).ingest(document)
            return ToolResult(content=json.dumps({
                "source_id": document.source_id, "name": document.name, "sha256": document.sha256,
                "characters": len(document.text), "chunks_indexed": count,
                "index_path": ".agentforge/knowledge.sqlite3",
            }, ensure_ascii=False))
        except ToolError:
            raise
        except (ValueError, OSError) as exc:
            raise ToolError(f"Knowledge ingestion failed: {exc}") from exc


class KnowledgeSearchTool(Tool):
    kind = "knowledge_search"
    default_description = (
        "Search the persistent project knowledge index by meaning-bearing keywords. Returns ranked snippets "
        "with source names and character offsets; use the source file for full context before making edits."
    )
    Input = KnowledgeSearchInput
    permissions: set[Permission] = set()

    async def run(self, args: KnowledgeSearchInput, ctx: ToolContext) -> ToolResult:
        hits = _index(ctx).search(args.query, limit=args.limit)
        return ToolResult(content=json.dumps([
            {
                "source": hit.chunk.source_name, "source_id": hit.chunk.source_id,
                "chunk_id": hit.chunk.chunk_id, "score": round(hit.score, 5),
                "start_char": hit.chunk.start_char, "end_char": hit.chunk.end_char,
                "text": hit.chunk.text,
            } for hit in hits
        ], ensure_ascii=False))


class WorkspaceEditTool(Tool):
    kind = "workspace_edit"
    default_description = (
        "Apply precise UTF-8 text replacements to a workspace file. Always supply the current SHA-256 from "
        "a fresh read, and each exact target must occur exactly the requested number of times. The tool "
        "creates a backup, writes atomically, and records an edit history for rollback."
    )
    Input = WorkspaceEditInput
    permissions: set[Permission] = {"fs_write"}

    async def run(self, args: WorkspaceEditInput, ctx: ToolContext) -> ToolResult:
        editor = SafeWorkspaceEditor(ctx.workspace.root)
        try:
            applied = editor.apply_replacements(
                args.path,
                [TextReplacement(
                    expected_text=item.expected_text,
                    replacement_text=item.replacement_text,
                    expected_count=item.expected_count,
                ) for item in args.replacements],
                expected_sha256=args.expected_sha256,
                actor=ctx.agent_id if hasattr(ctx, "agent_id") else "agent",
                reason=args.reason,
            )
            return ToolResult(content=json.dumps({
                "edit_id": applied.edit_id, "path": applied.path,
                "backup_path": applied.backup_path, "original_sha256": applied.original_sha256,
                "new_sha256": applied.new_sha256, "changed_at": applied.changed_at,
            }, ensure_ascii=False))
        except EditConflict as exc:
            raise ToolError(f"Edit conflict; nothing was changed. {exc}") from exc
        except EditError as exc:
            raise ToolError(f"Edit rejected; nothing was changed. {exc}") from exc
        except (OSError, UnicodeError) as exc:
            raise ToolError(f"Workspace edit failed: {exc}") from exc


class ToolFactoryLike(Protocol):
    def build(self, binding: Any) -> Tool: ...


class WorkspaceCapabilityToolFactory:
    """Adds the shared built-ins while delegating all existing tool kinds unchanged."""

    _BUILTINS = {
        "knowledge_ingest": KnowledgeIngestTool,
        "knowledge_search": KnowledgeSearchTool,
        "workspace_edit": WorkspaceEditTool,
    }

    def __init__(self, delegate: ToolFactoryLike):
        self.delegate = delegate

    def build(self, binding: Any) -> Tool:
        tool_cls = self._BUILTINS.get(str(binding.kind).casefold())
        if tool_cls is not None:
            return tool_cls()
        return self.delegate.build(binding)
