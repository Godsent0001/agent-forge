from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

from app.tools.web_search import WebSearchTool, _free_search_backend


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
        def __init__(self, *, timeout: int):
            assert timeout == 12

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def text(self, query: str, *, max_results: int, backend: str):
            assert query == "agentforge"
            assert max_results == 8
            assert backend == "auto"
            return [{"title": "AgentForge", "href": "https://example.com", "body": "Result"}]

    fake_module = ModuleType("ddgs")
    fake_module.DDGS = FakeDDGS
    monkeypatch.setitem(sys.modules, "ddgs", fake_module)
    monkeypatch.delenv("CRAWL4AI_KEY", raising=False)

    results = await _free_search_backend("agentforge")
    assert results == [{
        "title": "AgentForge",
        "url": "https://example.com",
        "snippet": "Result",
    }]


@pytest.mark.asyncio
async def test_search_falls_back_to_keyless_html_backend_when_ddgs_fails(monkeypatch):
    class BrokenDDGS:
        def __init__(self, *, timeout: int):
            raise RuntimeError("simulated DDGS connection failure")

    fake_module = ModuleType("ddgs")
    fake_module.DDGS = BrokenDDGS
    monkeypatch.setitem(sys.modules, "ddgs", fake_module)
    monkeypatch.delenv("CRAWL4AI_KEY", raising=False)

    async def html_search(query: str) -> list[dict[str, str]]:
        assert query == "power tank price"
        return [{"title": "Example result", "url": "https://example.com/price", "snippet": "Listed price"}]

    monkeypatch.setattr("app.tools.web_search._duckduckgo_html_search_backend", html_search)
    results = await _free_search_backend("power tank price")
    assert results[0]["url"] == "https://example.com/price"


def test_ddg_html_parser_extracts_external_result_links_and_snippets():
    from app.tools.web_search import _parse_ddg_html_results

    html = '''
    <div class="result">
      <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fprice">Power tank <b>price</b></a>
      <a class="result__snippet">Current listed price and availability.</a>
    </div>
    '''
    results = _parse_ddg_html_results(html)
    assert results == [{
        "title": "Power tank price",
        "url": "https://example.com/price",
        "snippet": "Current listed price and availability.",
    }]


@pytest.mark.asyncio
async def test_serper_is_primary_when_key_is_configured(monkeypatch):
    from app.tools.web_search import WebSearchTool

    monkeypatch.setenv("SERPER_API_KEY", "test-key")
    calls = []

    async def serper(query):
        calls.append(("serper", query))
        return [{"title": "Serper result", "url": "https://example.com", "snippet": "Found"}]

    async def free(query):
        calls.append(("free", query))
        return []

    monkeypatch.setattr("app.tools.web_search._serper_search_backend", serper)
    monkeypatch.setattr("app.tools.web_search._free_search_backend", free)
    results = await WebSearchTool()._search_with_fallback("test query")
    assert results[0]["title"] == "Serper result"
    assert calls == [("serper", "test query")]


@pytest.mark.asyncio
async def test_search_uses_free_fallback_when_serper_fails(monkeypatch):
    from app.tools.web_search import WebSearchTool

    monkeypatch.setenv("SERPER_API_KEY", "test-key")
    calls = []

    async def serper(query):
        calls.append("serper")
        raise RuntimeError("simulated Serper outage")

    async def free(query):
        calls.append("free")
        return [{"title": "Free result", "url": "https://example.com", "snippet": "Fallback"}]

    monkeypatch.setattr("app.tools.web_search._serper_search_backend", serper)
    monkeypatch.setattr("app.tools.web_search._free_search_backend", free)
    results = await WebSearchTool()._search_with_fallback("test query")
    assert results[0]["title"] == "Free result"
    assert calls == ["serper", "free"]
