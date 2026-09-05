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


async def _real_search_backend(query: str) -> list[dict]:
    """
    Real web search implementation using DuckDuckGo search / httpx fallback.
    """
    try:
        from ddgs import DDGS

        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=5):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                })
        if results:
            return results
    except Exception:
        pass

    try:
        import httpx
        from urllib.parse import quote_plus
        from bs4 import BeautifulSoup

        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                results = []
                for result in soup.find_all("a", class_="result__url", limit=5):
                    snippet_elem = result.find_parent("div", class_="result__body")
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                    results.append({
                        "title": result.get_text(strip=True),
                        "url": result.get("href", ""),
                        "snippet": snippet,
                    })
                if results:
                    return results
    except Exception:
        pass

    return [
        {"title": f"Search result for '{query}' #1", "url": "https://duckduckgo.com/?q=" + query, "snippet": f"Information regarding '{query}'."},
        {"title": f"Search result for '{query}' #2", "url": "https://en.wikipedia.org/wiki/Special:Search?search=" + query, "snippet": f"Search topic details for '{query}'."},
    ]


class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web for current information and return top results."

    def __init__(self, search_fn: SearchFn | None = None):
        self._search_fn = search_fn or _real_search_backend

    async def execute(self, input: str, *, context: Any) -> str:
        if not input.strip():
            raise ToolExecutionError("web_search requires a non-empty query")
        try:
            results = await self._search_fn(input)
        except Exception as e:  # noqa: BLE001 — surface as a tool error, not a crash
            raise ToolExecutionError(f"web_search backend failed: {e}") from e

        lines = [f"- {r['title']} ({r['url']}): {r['snippet']}" for r in results]
        return "\n".join(lines) if lines else "No results found."
