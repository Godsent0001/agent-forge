from __future__ import annotations

import pytest

from app.core.embeddings import _embed_cached, embed_text


def test_venice_embedding_uses_configured_api_endpoint(monkeypatch):
    import httpx

    monkeypatch.setenv("VENICE_API_KEY", "test-key")
    calls = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [{"embedding": [0.1, 0.2, 0.3]}]}

    class FakeClient:
        def __init__(self, **kwargs):
            calls["client"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, **kwargs):
            calls["url"] = url
            calls["request"] = kwargs
            return FakeResponse()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    _embed_cached.cache_clear()
    try:
        vector = embed_text("AgentForge embedding test", "venice/text-embedding-bge-m3")
    finally:
        _embed_cached.cache_clear()

    assert vector == [0.1, 0.2, 0.3]
    assert calls["url"] == "https://api.venice.ai/api/v1/embeddings"
    assert calls["request"]["headers"] == {"Authorization": "Bearer test-key"}
    assert calls["request"]["json"] == {"model": "text-embedding-bge-m3", "input": ["AgentForge embedding test"]}


def test_venice_embedding_requires_api_key(monkeypatch):
    monkeypatch.delenv("VENICE_API_KEY", raising=False)
    _embed_cached.cache_clear()
    with pytest.raises(RuntimeError, match="VENICE_API_KEY"):
        embed_text("AgentForge embedding test", "venice/text-embedding-bge-m3")
    _embed_cached.cache_clear()
