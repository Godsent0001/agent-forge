"""Search a saved shell log using exact/keyword search and optional semantic reranking."""
from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any, Callable

from app.core.embeddings import DEFAULT_EMBEDDING_MODEL, embed_text
from app.tools.base import Tool, ToolExecutionError

MAX_LOG_BYTES = 2_000_000
CHUNK_CHARS = 2400
MAX_SEMANTIC_CHUNKS = 200
MAX_RESULTS = 5


def _chunks(text: str) -> list[tuple[int, str]]:
    lines = text.splitlines()
    chunks: list[tuple[int, str]] = []
    start = 0
    while start < len(lines):
        end = start
        body: list[str] = []
        size = 0
        while end < len(lines) and (size + len(lines[end]) + 1 <= CHUNK_CHARS or not body):
            body.append(lines[end])
            size += len(lines[end]) + 1
            end += 1
        chunks.append((start + 1, "\n".join(body)))
        start = max(start + 1, end - 2)
    return chunks


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def _lexical_score(query: str, text: str) -> float:
    terms = {term.casefold() for term in query.split() if len(term) > 1}
    if not terms:
        return 0.0
    lowered = text.casefold()
    return sum(1 for term in terms if term in lowered) / len(terms)


class LogSearchTool(Tool):
    name = "log_search"
    description = (
        "Search a saved shell log using exact/keyword matches and optional local or provider embeddings. "
        "Input format: '<workspace-relative-log-path>::<question or search terms>'."
    )

    def __init__(self, embedding_fn: Callable[[str], list[float]] | None = None) -> None:
        self._embedding_fn = embedding_fn or (lambda text: embed_text(text, os.environ.get("AGENTFORGE_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)))

    async def execute(self, input: str, *, context: Any) -> str:
        if "::" not in input:
            raise ToolExecutionError("log_search input must be '<relative path>::<query>'")
        rel_path, query = input.split("::", 1)
        query = query.strip()
        if not query:
            raise ToolExecutionError("log_search requires a non-empty query")
        workspace = getattr(context, "workspace", None)
        if workspace is None or not hasattr(workspace, "resolve"):
            raise ToolExecutionError("log_search requires a run workspace")
        try:
            path: Path = workspace.resolve(rel_path.strip())
        except Exception as exc:
            raise ToolExecutionError(f"invalid workspace log path: {exc}") from exc
        if not path.is_file():
            raise ToolExecutionError("log file not found in the run workspace")
        if path.stat().st_size > MAX_LOG_BYTES:
            raise ToolExecutionError(f"log exceeds the {MAX_LOG_BYTES}-byte search limit")
        text = path.read_text(encoding="utf-8", errors="replace")
        chunks = _chunks(text)
        if not chunks:
            return "The log is empty."

        query_vector: list[float] | None = None
        chunk_vectors: dict[int, list[float]] = {}
        if len(chunks) <= MAX_SEMANTIC_CHUNKS:
            try:
                query_vector = self._embedding_fn(query)
                if query_vector:
                    for index, (_, chunk_text) in enumerate(chunks):
                        chunk_vectors[index] = self._embedding_fn(chunk_text)
            except Exception:
                # Exact/keyword search remains available if a model or API is unavailable.
                query_vector = None
                chunk_vectors.clear()

        ranked = []
        for index, (line_start, chunk_text) in enumerate(chunks):
            lexical = _lexical_score(query, chunk_text)
            semantic = max(0.0, _cosine(query_vector, chunk_vectors[index])) if query_vector and index in chunk_vectors else 0.0
            score = 0.7 * lexical + 0.3 * semantic if query_vector else lexical
            if score > 0:
                ranked.append((score, lexical, semantic, line_start, chunk_text))
        ranked.sort(key=lambda item: item[0], reverse=True)
        if not ranked:
            return "No relevant log sections found. Try an exact error code, filename, or different wording."

        results = []
        for rank, (score, lexical, semantic, line_start, chunk_text) in enumerate(ranked[:MAX_RESULTS], 1):
            end_line = line_start + chunk_text.count("\n")
            excerpt = chunk_text[:1400]
            if len(chunk_text) > 1400:
                excerpt += "…[excerpt truncated]"
            results.append(
                f"[{rank}] lines {line_start}-{end_line} (score={score:.3f}, keyword={lexical:.3f}, semantic={semantic:.3f})\n{excerpt}"
            )
        method = "hybrid keyword + embedding" if query_vector else "keyword"
        return f"Search method: {method}\nMatching sections: {len(ranked)}\n\n" + "\n\n".join(results)
