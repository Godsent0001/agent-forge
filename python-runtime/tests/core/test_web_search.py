from __future__ import annotations

import asyncio
import sys
import types
from typing import Any

import pytest

from app.tools.base import ToolExecutionError
from app.tools.web_search import WebSearchTool, _ddgs_search_backend


class FakeDDGS:
    calls: list[tuple[str, int, str]] = []
    timeouts: list[int] = []

    def __init__(self, *args: Any, **kwargs: Any):
        self.timeouts.append(kwargs.get("timeout"))

    def __enter__(self):
        return self

    def __exit__(self, *args: Any):
        return False

    def text(self, query: str, max_results: int = 8, backend: str = "auto"):
        self.calls.append((query, max_results, backend))
        return [
            {"title": "Example result", "href": "https://example.com", "body": "Relevant snippet"},
            {"title": "Second result", "url": "https://example.org", "snippet": "Another snippet"},
        ]


@pytest.mark.asyncio
async def test_free_ddgs_backend_maps_results_without_api_key(monkeypatch: pytest.MonkeyPatch):
    FakeDDGS.calls.clear()
    FakeDDGS.timeouts.clear()
    monkeypatch.delenv("CRAWL4AI_KEY", raising=False)
    monkeypatch.setitem(sys.modules, "ddgs", types.SimpleNamespace(DDGS=FakeDDGS))

    results = await _ddgs_search_backend("power tank price Nigeria")

    assert FakeDDGS.calls == [("power tank price Nigeria", 8, "auto")]
    assert FakeDDGS.timeouts == [12]
    assert results == [
        {"title": "Example result", "url": "https://example.com", "snippet": "Relevant snippet"},
        {"title": "Second result", "url": "https://example.org", "snippet": "Another snippet"},
    ]


@pytest.mark.asyncio
async def test_web_search_formats_results_for_agent():
    async def search(query: str):
        assert query == "power tank price Nigeria"
        return [{"title": "Product listing", "url": "https://example.com/item", "snippet": "₦25,000"}]

    result = await WebSearchTool(search_fn=search).execute(
        "  power tank price Nigeria  ",
        context=types.SimpleNamespace(),
    )

    assert "Product listing" in result
    assert "https://example.com/item" in result
    assert "₦25,000" in result


@pytest.mark.asyncio
async def test_web_search_surfaces_backend_failure_instead_of_empty_success():
    async def broken_search(query: str):
        raise RuntimeError("upstream timeout")

    with pytest.raises(ToolExecutionError, match="backend failed: upstream timeout"):
        await WebSearchTool(search_fn=broken_search).execute(
            "power tank price Nigeria",
            context=types.SimpleNamespace(),
        )


@pytest.mark.asyncio
async def test_web_search_rejects_empty_query():
    with pytest.raises(ToolExecutionError, match="non-empty query"):
        await WebSearchTool(search_fn=lambda _: asyncio.sleep(0, result=[])).execute(
            "   ",
            context=types.SimpleNamespace(),
        )
