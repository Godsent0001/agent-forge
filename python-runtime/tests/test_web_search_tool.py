from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

from app.tools.web_search import WebSearchTool, _ddgs_search_backend


@pytest.mark.asyncio
async def test_web_search_supports_injected_backend_without_provider_key():
    async def fake_search(query: str) -> list[dict[str, str]]:
        assert query == "python docs"
        return [{"title": "Python", "url": "https://python.org", "snippet": "Docs"}]

    result = await WebSearchTool(search_fn=fake_search).execute(
        "  python docs  ", context=SimpleNamespace()
    )
    assert "https://python.org" in result
    assert "Docs" in result


@pytest.mark.asyncio
async def test_default_search_uses_ddgs_without_api_key(monkeypatch):
    class FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def text(self, query: str, *, max_results: int):
            assert query == "agentforge"
            assert max_results == 8
            return [{"title": "AgentForge", "href": "https://example.com", "body": "Result"}]

    fake_module = ModuleType("ddgs")
    fake_module.DDGS = FakeDDGS
    monkeypatch.setitem(sys.modules, "ddgs", fake_module)
    monkeypatch.delenv("CRAWL4AI_KEY", raising=False)

    results = await _ddgs_search_backend("agentforge")
    assert results == [{
        "title": "AgentForge",
        "url": "https://example.com",
        "snippet": "Result",
    }]
