"""Summarize tool for condensing large files and artifacts."""
from typing import Any, ClassVar
from pydantic import BaseModel, Field

from app.contracts.tools import Tool, ToolError, ToolResult


class SummarizeInput(BaseModel):
    source: str = Field(description="Workspace relative path or artifact handle to summarize")
    focus: str | None = Field(default=None, description="Optional focus area or question")


class SummarizeTool(Tool):
    """Tool to condense large workspace files into structured summaries."""

    kind: ClassVar[str] = "summarize"
    default_description: ClassVar[str] = "Summarize a large workspace file or artifact."
    Input: ClassVar[type[BaseModel]] = SummarizeInput

    def __init__(self, llm_complete_fn: Any = None):
        self.llm_complete_fn = llm_complete_fn

    async def run(self, args: SummarizeInput, ctx: Any) -> ToolResult:
        if not hasattr(ctx, "workspace") or not ctx.workspace:
            raise ToolError("Workspace context unavailable.")

        try:
            target_path = ctx.workspace.resolve(args.source)
            if not target_path.is_file():
                raise ToolError(f"File not found: '{args.source}'")

            text = target_path.read_text(encoding="utf-8", errors="replace")
        except ToolError:
            raise
        except Exception as e:
            raise ToolError(f"Failed to read file '{args.source}': {e}")

        if not text.strip():
            return ToolResult(ok=True, content="File is empty.")

        chunk_size = 8000
        overlap = 500
        chunks = []
        i = 0
        while i < len(text):
            chunks.append(text[i : i + chunk_size])
            i += chunk_size - overlap

        if len(chunks) > 50:
            raise ToolError("File is too large to summarize (>50 chunks).")

        chunk_summaries = []
        for idx, chunk in enumerate(chunks, 1):
            if self.llm_complete_fn:
                prompt = (
                    f"Summarize chunk {idx}/{len(chunks)} of file '{args.source}'.\n"
                    f"Focus: {args.focus or 'General key points'}\n\n"
                    f"Text:\n{chunk}"
                )
                try:
                    turn = await self.llm_complete_fn([{"role": "user", "content": prompt}])
                    chunk_summaries.append(turn.text or chunk[:200])
                except Exception:
                    chunk_summaries.append(chunk[:200] + "...")
            else:
                chunk_summaries.append(chunk[:200] + "...")

        final_summary = "\n\n".join(chunk_summaries)
        return ToolResult(ok=True, content=f"Summary of {args.source}:\n{final_summary}")
