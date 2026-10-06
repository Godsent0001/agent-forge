"""Doc search tool for searching codebase and text files by query."""
import re
from pathlib import Path
from typing import Any, ClassVar
from pydantic import BaseModel, Field

from app.contracts.tools import Tool, ToolError, ToolResult


class DocSearchInput(BaseModel):
    source: str = Field(description="Workspace relative path to file or directory to search")
    query: str = Field(description="Search terms or query")
    limit: int = Field(default=5, description="Maximum number of matches")


class DocSearchTool(Tool):
    """Tool to search within text and source code files."""

    kind: ClassVar[str] = "doc_search"
    default_description: ClassVar[str] = "Search for query matches within workspace files."
    Input: ClassVar[type[BaseModel]] = DocSearchInput

    async def run(self, args: DocSearchInput, ctx: Any) -> ToolResult:
        if not hasattr(ctx, "workspace") or not ctx.workspace:
            raise ToolError("Workspace context unavailable.")

        try:
            target_path = ctx.workspace.resolve(args.source)
        except Exception as e:
            raise ToolError(f"Path resolution error: {e}")

        files_to_search: list[Path] = []
        if target_path.is_file():
            files_to_search.append(target_path)
        elif target_path.is_dir():
            files_to_search.extend([p for p in target_path.rglob("*") if p.is_file() and not p.name.startswith(".")])
        else:
            raise ToolError(f"Target path '{args.source}' does not exist.")

        query_terms = [t for t in re.split(r"\W+", args.query.lower()) if t]
        results = []

        for file_path in files_to_search:
            try:
                rel_str = ctx.workspace.relative(file_path)
                lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
                for line_idx, line in enumerate(lines, 1):
                    line_lower = line.lower()
                    matches = sum(1 for term in query_terms if term in line_lower)
                    if matches > 0:
                        score = matches / max(1, len(query_terms))
                        results.append((score, rel_str, line_idx, line.strip()))
            except Exception:
                continue

        results.sort(key=lambda x: x[0], reverse=True)
        top_matches = results[: args.limit]

        if not top_matches:
            return ToolResult(ok=True, content=f"No matches found for '{args.query}' in '{args.source}'.")

        lines = [f"Matches for '{args.query}':"]
        for score, rel, line_num, snippet in top_matches:
            lines.append(f"- {rel}:{line_num}: {snippet[:200]}")

        return ToolResult(ok=True, content="\n".join(lines))
