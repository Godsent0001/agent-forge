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
