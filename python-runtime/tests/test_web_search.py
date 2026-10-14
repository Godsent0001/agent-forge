import pytest

from app.tools.base import ToolExecutionError
from app.tools.web_search import WebSearchTool, _crawl4ai_search_backend


@pytest.mark.asyncio
async def test_web_search_formats_injected_crawl4ai_results():
    async def search_fn(query):
        assert query == "latest agent frameworks"
        return [
            {
                "title": "Example result",
                "url": "https://example.com/article",
                "snippet": "Example snippet",
            }
        ]

    tool = WebSearchTool(search_fn=search_fn)

    result = await tool.execute("latest agent frameworks", context=None)

    assert result == "- Example result (https://example.com/article): Example snippet"


@pytest.mark.asyncio
async def test_web_search_rejects_empty_query():
    tool = WebSearchTool(search_fn=lambda _: None)

    with pytest.raises(ToolExecutionError, match="non-empty query"):
        await tool.execute("   ", context=None)


@pytest.mark.asyncio
async def test_crawl4ai_backend_requires_key(monkeypatch):
    monkeypatch.delenv("CRAWL4AI_KEY", raising=False)

    with pytest.raises(ToolExecutionError, match="CRAWL4AI_KEY"):
        await _crawl4ai_search_backend("agentforge")


@pytest.mark.asyncio
async def test_crawl4ai_backend_maps_ranked_results(monkeypatch):
    monkeypatch.setenv("CRAWL4AI_KEY", "test-key")
    calls = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "results": [
                    {
                        "title": "First",
                        "url": "https://example.com/1",
                        "snippet": "One",
                        "source": "gg",
                    },
                    {
                        "title": "Second",
                        "url": "https://example.com/2",
                        "snippet": "Two",
                    },
                ]
            }

    class FakeClient:
        def __init__(self, **kwargs):
            calls["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, **kwargs):
            calls["url"] = url
            calls["request"] = kwargs
            return FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    results = await _crawl4ai_search_backend("agentforge")

    assert calls["url"] == "https://api.crawl4ai.com/search"
    assert calls["request"]["params"] == {"q": "agentforge"}
    assert calls["request"]["headers"] == {"Authorization": "Bearer test-key"}
    assert results == [
        {
            "title": "First",
            "url": "https://example.com/1",
            "snippet": "One",
        },
        {
            "title": "Second",
            "url": "https://example.com/2",
            "snippet": "Two",
        },
    ]
