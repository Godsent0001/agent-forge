"""Web search tool backed by Crawl4AI Cloud.

Crawl4AI provides a ranked web-search endpoint. AgentForge keeps the backend
pluggable so tests can inject a deterministic search function without network
access.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from typing import Any

from app.tools.base import Tool, ToolExecutionError

SearchFn = Callable[[str], Awaitable[list[dict[str, str]]]]


async def _crawl4ai_search_backend(query: str) -> list[dict[str, str]]:
    """Search through the Crawl4AI Cloud /search endpoint."""
    key = os.environ.get("CRAWL4AI_KEY")
    if not key:
        raise ToolExecutionError(
            "web_search requires CRAWL4AI_KEY for the Crawl4AI search backend."
        )

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
    except ToolExecutionError:
        raise
    except Exception as exc:  # noqa: BLE001 — normalize network/backend failures
        raise ToolExecutionError(f"Crawl4AI search backend failed: {exc}") from exc

    raw_results = payload.get("results", []) if isinstance(payload, dict) else []
    results: list[dict[str, str]] = []
    for item in raw_results[:10]:
        if not isinstance(item, dict):
            continue
        results.append({
            "title": str(item.get("title", "")),
            "url": str(item.get("url", "")),
            "snippet": str(item.get("snippet", "")),
        })
    return results


class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web using Crawl4AI and return ranked source results."

    def __init__(self, search_fn: SearchFn | None = None):
        self._search_fn = search_fn or _crawl4ai_search_backend

    async def execute(self, input: str, *, context: Any) -> str:
        if not input.strip():
            raise ToolExecutionError("web_search requires a non-empty query")
        try:
            results = await self._search_fn(input.strip())
        except ToolExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001 — normalize injected backend failures
            raise ToolExecutionError(f"web_search backend failed: {exc}") from exc

        lines = [
            f"- {item['title']} ({item['url']}): {item['snippet']}"
            for item in results
        ]
        return "\n".join(lines) if lines else "No results found."
