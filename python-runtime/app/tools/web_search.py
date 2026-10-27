"""Free web search with an optional configured Crawl4AI fallback.

The default backend uses the open-source `ddgs` Python package and does not
require a paid API key. Crawl4AI Cloud is only used when explicitly configured.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any

from app.tools.base import Tool, ToolExecutionError

SearchFn = Callable[[str], Awaitable[list[dict[str, str]]]]


async def _ddgs_search_backend(query: str) -> list[dict[str, str]]:
    """Search using the open-source DDGS client without an API key."""
    try:
        from ddgs import DDGS

        def search() -> list[dict[str, str]]:
            with DDGS() as client:
                raw_results = client.text(query, max_results=8)
                return [
                    {
                        "title": str(item.get("title", "")),
                        "url": str(item.get("href", item.get("url", ""))),
                        "snippet": str(item.get("body", item.get("snippet", ""))),
                    }
                    for item in raw_results
                    if isinstance(item, dict)
                ]

        return await asyncio.to_thread(search)
    except Exception as exc:  # noqa: BLE001 — normalize upstream failures
        # A configured Crawl4AI key is an explicit opt-in fallback, never a requirement.
        if os.environ.get("CRAWL4AI_KEY"):
            return await _crawl4ai_search_backend(query)
        raise ToolExecutionError(
            "Free web search failed. Check your internet connection or try again. "
            f"Details: {exc}"
        ) from exc


async def _crawl4ai_search_backend(query: str) -> list[dict[str, str]]:
    """Search through Crawl4AI Cloud when a user explicitly configured it."""
    key = os.environ.get("CRAWL4AI_KEY")
    if not key:
        raise ToolExecutionError("Crawl4AI fallback is not configured. Set CRAWL4AI_KEY to enable this optional fallback.")

    base_url = os.environ.get("CRAWL4AI_URL", "https://api.crawl4ai.com").rstrip("/")
    try:
        import httpx

        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(
                f"{base_url}/search",
                params={"q": query},
                headers={"Authorization": f"Bearer {key}"},
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:  # noqa: BLE001 — normalize network/backend failures
        raise ToolExecutionError(f"Crawl4AI fallback failed: {exc}") from exc

    raw_results = payload.get("results", []) if isinstance(payload, dict) else []
    return [
        {
            "title": str(item.get("title", "")),
            "url": str(item.get("url", "")),
            "snippet": str(item.get("snippet", "")),
        }
        for item in raw_results[:8]
        if isinstance(item, dict)
    ]


class WebSearchTool(Tool):
    name = "web_search"
    description = (
        "Search the web for ranked sources using free, keyless DDGS search. "
        "An explicitly configured Crawl4AI key can be used as a fallback."
    )

    def __init__(self, search_fn: SearchFn | None = None):
        self._search_fn = search_fn or _ddgs_search_backend

    async def execute(self, input: str, *, context: Any) -> str:
        query = input.strip()
        if not query:
            raise ToolExecutionError("web_search requires a non-empty query")
        try:
            results = await self._search_fn(query)
        except ToolExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001 — normalize injected backend failures
            raise ToolExecutionError(f"web_search backend failed: {exc}") from exc

        lines = [
            f"- {item['title']} ({item['url']}): {item['snippet']}"
            for item in results
        ]
        return "\n".join(lines) if lines else "No results found."
