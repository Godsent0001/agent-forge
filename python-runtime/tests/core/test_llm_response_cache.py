from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.llm import response_cache


def test_response_cache_expires_and_evicts(monkeypatch):
    monkeypatch.setattr(response_cache, "CACHE_TTL_SECONDS", 5)
    monkeypatch.setattr(response_cache, "CACHE_MAX_ENTRIES", 2)
    response_cache.clear_cache()
    response_cache.set_cached("a", "one", now=10)
    assert response_cache.get_cached("a", now=14) == "one"
    assert response_cache.get_cached("a", now=15) is None
    response_cache.set_cached("b", "two", now=20)
    response_cache.set_cached("c", "three", now=20)
    response_cache.set_cached("d", "four", now=20)
    assert response_cache.get_cached("b", now=21) is None
    assert response_cache.get_cached("d", now=21) == "four"


@pytest.mark.asyncio
async def test_adapter_reuses_identical_no_tool_completion(monkeypatch):
    import litellm

    from app.core.llm import adapter
    from app.core.llm.types import LLMParams

    response_cache.clear_cache()
    calls = {"count": 0}

    async def fake_acompletion(**kwargs):
        calls["count"] += 1
        return SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(role="assistant", content="cached answer", tool_calls=[]),
                finish_reason="stop",
            )],
            usage=SimpleNamespace(prompt_tokens=12, completion_tokens=4, prompt_tokens_details=None),
        )

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    messages = [{"role": "user", "content": "Explain a stable programming concept."}]
    first = await adapter.complete(messages, model="venice/deepseek-v4-1-flash-uncensored", params=LLMParams(temperature=0))
    second = await adapter.complete(messages, model="venice/deepseek-v4-1-flash-uncensored", params=LLMParams(temperature=0))

    assert first.text == second.text == "cached answer"
    assert first.cached is False
    assert second.cached is True
    assert second.usage.input_tokens == 0
    assert second.usage.output_tokens == 0
    assert second.cost_usd == 0.0
    assert calls["count"] == 1
