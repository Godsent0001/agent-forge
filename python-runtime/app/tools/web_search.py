"""Free web search with an optional configured Crawl4AI fallback.

The default backend uses the open-source `ddgs` Python package and does not
require a paid API key. Crawl4AI Cloud is only used when explicitly configured.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from app.tools.base import Tool, ToolExecutionError

SearchFn = Callable[[str], Awaitable[list[dict[str, str]]]]


class _DuckDuckGoHTMLParser(HTMLParser):
    """Extract organic result titles, links, and snippets from DDG's HTML endpoint."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._capture: tuple[str, int] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        if tag == "a" and "result__a" in classes:
            self.results.append({
                "title": "",
                "url": values.get("href") or "",
                "snippet": "",
            })
            self._capture = ("title", len(self.results) - 1)
        elif self.results and "result__snippet" in classes:
            self._capture = ("snippet", len(self.results) - 1)

    def handle_data(self, data: str) -> None:
        if self._capture is None:
            return
        field, index = self._capture
        self.results[index][field] += data

    def handle_endtag(self, tag: str) -> None:
        if self._capture is None:
            return
        field, _ = self._capture
        if (field == "title" and tag == "a") or (field == "snippet" and tag in {"a", "div"}):
            self._capture = None


def _parse_ddg_html_results(document: str, limit: int = 8) -> list[dict[str, str]]:
    parser = _DuckDuckGoHTMLParser()
    parser.feed(document)
    results: list[dict[str, str]] = []
    for item in parser.results:
        raw_url = item["url"].strip()
        parsed = urlparse(raw_url)
        query = parse_qs(parsed.query)
        target = query.get("uddg", [raw_url])[0]
        target = unquote(target).strip()
        if not target.startswith(("https://", "http://")):
            continue
        if not item["title"].strip():
            continue
        results.append({
            "title": " ".join(item["title"].split()),
            "url": target,
            "snippet": " ".join(item["snippet"].split()),
        })
        if len(results) >= limit:
            break
    return results


async def _duckduckgo_html_search_backend(query: str) -> list[dict[str, str]]:
    """Independent, keyless fallback when DDGS's metasearch client fails."""
    import httpx

    async with httpx.AsyncClient(
        timeout=15.0,
        follow_redirects=True,
        headers={"User-Agent": "AgentForge/1.0 (open-source desktop research client)"},
    ) as client:
        response = await client.get("https://html.duckduckgo.com/html/", params={"q": query})
        response.raise_for_status()
    results = _parse_ddg_html_results(response.text)
    if not results:
        raise ToolExecutionError("DuckDuckGo HTML returned no parseable search results.")
    return results


async def _ddgs_search_backend(query: str) -> list[dict[str, str]]:
    """Search without a paid key, falling back to a separate keyless HTML endpoint."""
    failures: list[str] = []
    try:
        from ddgs import DDGS

        def search() -> list[dict[str, str]]:
            with DDGS(timeout=12) as client:
                raw_results = client.text(query, max_results=8, backend="auto")
                return [
                    {
                        "title": str(item.get("title", "")),
                        "url": str(item.get("href", item.get("url", ""))),
                        "snippet": str(item.get("body", item.get("snippet", ""))),
                    }
                    for item in raw_results
                    if isinstance(item, dict)
                ]

        results = await asyncio.to_thread(search)
        if results:
            return results
        failures.append("DDGS returned no results")
    except Exception as exc:  # noqa: BLE001 — preserve failure while trying fallback
        failures.append(f"DDGS {type(exc).__name__}: {str(exc)[:240]}")

    try:
        results = await _duckduckgo_html_search_backend(query)
        if results:
            return results
        failures.append("DuckDuckGo HTML returned no results")
    except Exception as exc:  # noqa: BLE001 — normalize upstream failures
        failures.append(f"DuckDuckGo HTML {type(exc).__name__}: {str(exc)[:240]}")

    if os.environ.get("CRAWL4AI_KEY"):
        try:
            results = await _crawl4ai_search_backend(query)
            if results:
                return results
            failures.append("configured Crawl4AI fallback returned no results")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"Crawl4AI {type(exc).__name__}: {str(exc)[:240]}")

    raise ToolExecutionError(
        "Free web search failed across the available backends. "
        + "; ".join(failures)
        + ". Check connectivity or retry later; no search result was verified."
    )


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
