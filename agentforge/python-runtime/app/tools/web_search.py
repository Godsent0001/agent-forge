"""
Web Search tool.

The actual search backend (Bing/SerpAPI/Brave/etc.) is intentionally
pluggable via a `search_fn` — this environment has no network access to
test a real HTTP call, so a mock backend is wired by default. Swap in a
real HTTP client (e.g. httpx) behind the same `search_fn` signature when
you have API credentials.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.tools.base import Tool, ToolExecutionError

SearchFn = Callable[[str], Awaitable[list[dict]]]


async def _mock_search_backend(query: str) -> list[dict]:
    return [
        {"title": f"Mock result for '{query}' #1", "url": "https://example.com/1", "snippet": "..."},
        {"title": f"Mock result for '{query}' #2", "url": "https://example.com/2", "snippet": "..."},
    ]


class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web for current information and return top results."

    def __init__(self, search_fn: SearchFn | None = None):
        self._search_fn = search_fn or _mock_search_backend

    async def execute(self, input: str, *, context: Any) -> str:
        if not input.strip():
            raise ToolExecutionError("web_search requires a non-empty query")
        try:
            results = await self._search_fn(input)
        except Exception as e:  # noqa: BLE001 — surface as a tool error, not a crash
            raise ToolExecutionError(f"web_search backend failed: {e}") from e

        lines = [f"- {r['title']} ({r['url']}): {r['snippet']}" for r in results]
        return "\n".join(lines) if lines else "No results found."
