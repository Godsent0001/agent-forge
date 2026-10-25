import pytest

from app.core.llm.fake import FakeLLM
from app.core.llm.pricing import calculate_cost, get_context_window
from app.core.llm.types import (
    LLMTimeout,
    LLMTurn,
    ToolCall,
    Usage,
)


def test_pricing_and_catalog():
    assert get_context_window("anthropic/claude-3-5-sonnet-20241022") == 200000
    assert get_context_window("unknown_model", default=10000) == 10000

    usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000)
    cost = calculate_cost("anthropic/claude-3-5-sonnet-20241022", usage)
    assert cost == 18.0

    ollama_usage = Usage(input_tokens=500, output_tokens=200)
    assert calculate_cost("ollama/llama3.2", ollama_usage) == 0.0


@pytest.mark.asyncio
async def test_fake_llm_scripted_turns():
    llm = FakeLLM([
        LLMTurn(
            text="Hello world",
            tool_calls=[ToolCall(id="tc1", name="web_search", arguments={"query": "test"})],
            usage=Usage(input_tokens=10, output_tokens=20),
        ),
        LLMTimeout("Timed out"),
    ])

    turn1 = await llm.complete([{"role": "user", "content": "Hi"}])
    assert turn1.text == "Hello world"
    assert len(turn1.tool_calls) == 1
    assert turn1.tool_calls[0].name == "web_search"

    with pytest.raises(LLMTimeout):
        await llm.complete([{"role": "user", "content": "Hi again"}])

    assert len(llm.received_calls) == 2


def _litellm_error(cls_name: str, message: str = "boom"):
    import litellm

    cls = getattr(litellm, cls_name)
    return cls(message=message, llm_provider="anthropic", model="anthropic/claude-test")


@pytest.mark.parametrize("err_factory,expected", [
    (lambda: _litellm_error("ContextWindowExceededError", "prompt is too long"), "context"),
    (lambda: _litellm_error("RateLimitError"), "rate_limit"),
    (lambda: _litellm_error("AuthenticationError", "invalid x-api-key"), "auth"),
    (lambda: _litellm_error("BadRequestError", "messages: bad"), "bad_request"),
    # Bare numbers in unrelated errors must not be read as HTTP statuses.
    (lambda: RuntimeError("connection reset after sending 4000 bytes"), "other"),
    (lambda: RuntimeError("upstream said 4290 things"), "other"),
    (lambda: RuntimeError("Request timed out"), "timeout"),
])
def test_adapter_classifies_provider_errors(err_factory, expected):
    from app.core.llm.adapter import _classify_error

    assert _classify_error(err_factory()) == expected


@pytest.mark.asyncio
async def test_adapter_does_not_retry_authentication_errors(monkeypatch):
    import litellm

    from app.core.llm import adapter
    from app.core.llm.types import LLMBadRequest

    calls = {"n": 0}

    async def fake_acompletion(**kwargs):
        calls["n"] += 1
        raise _litellm_error("AuthenticationError", "invalid x-api-key")

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    with pytest.raises(LLMBadRequest, match="Provider settings"):
        await adapter.complete([{"role": "user", "content": "hi"}], model="anthropic/claude-test")
    assert calls["n"] == 1


def test_pricing_covers_current_models_via_litellm_table():
    usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000)
    for model in ("anthropic/claude-sonnet-5-5", "openai/gpt-5", "gemini/gemini-2.5-flash"):
        assert calculate_cost(model, usage) is not None, model
    assert get_context_window("anthropic/claude-sonnet-4-5") == 200000
    assert calculate_cost("madeup/not-a-model", usage) is None


def test_cached_prompt_tokens_are_billed_once_at_cache_rate():
    # claude-3-5-sonnet in models.yaml: $3 in, $15 out, $0.30 cache read per million.
    usage = Usage(input_tokens=1_000_000, output_tokens=0, cache_read_tokens=400_000)
    assert calculate_cost("anthropic/claude-3-5-sonnet-20241022", usage) == pytest.approx(0.6 * 3 + 0.4 * 0.3)
