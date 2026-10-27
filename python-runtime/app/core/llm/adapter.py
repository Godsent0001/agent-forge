"""LLM adapter v2 integrating LiteLLM / provider models with retries and typed errors."""
import asyncio
import json
from typing import Any

from .pricing import calculate_cost
from .response_cache import (
    cache_enabled,
    get_cached,
    is_cacheable_messages,
    make_cache_key,
    set_cached,
)
from .types import (
    LLMBadRequest,
    LLMContextTooLong,
    LLMError,
    LLMParams,
    LLMRateLimit,
    LLMTimeout,
    LLMTurn,
    ToolCall,
    ToolSpec,
    Usage,
)


async def complete(
    messages: list[dict[str, Any]],
    tools: list[ToolSpec] | None = None,
    params: LLMParams | None = None,
    model: str = "gpt-4o-mini",
    max_retries: int = 3,
) -> LLMTurn:
    """Call LLM backend with retries and error mapping."""
    if not model or not model.strip():
        raise LLMBadRequest("Empty model name provided.")

    params = params or LLMParams()
    cache_key = None
    if not tools and cache_enabled() and is_cacheable_messages(messages):
        cache_key = make_cache_key(
            model=model,
            messages=messages,
            temperature=params.temperature,
            max_tokens=params.max_tokens,
        )
        cached_turn = get_cached(cache_key)
        if cached_turn is not None:
            return cached_turn.model_copy(update={"usage": Usage(), "cost_usd": 0.0, "cached": True})
    tools_formatted = None
    if tools:
        tools_formatted = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    attempt = 0
    while True:
        try:
            import litellm

            kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": params.temperature,
            }
            if tools_formatted:
                kwargs["tools"] = tools_formatted
            if params.max_tokens is not None:
                kwargs["max_tokens"] = params.max_tokens

            response = await litellm.acompletion(**kwargs)
            turn = _parse_response(response, model)
            if cache_key is not None and not turn.tool_calls:
                set_cached(cache_key, turn.model_copy(deep=True))
            return turn

        except Exception as err:
            attempt += 1
            mapped = _map_error(err)
            if attempt > max_retries or not mapped.retryable:
                raise mapped from err
            await asyncio.sleep(min(2**attempt, 8))


def _parse_response(response: Any, model: str) -> LLMTurn:
    choice = response.choices[0]
    message = choice.message
    usage_raw = getattr(response, "usage", None)
    usage = Usage(
        input_tokens=getattr(usage_raw, "prompt_tokens", 0) or 0,
        output_tokens=getattr(usage_raw, "completion_tokens", 0) or 0,
    )
    tool_calls = []
    for call in getattr(message, "tool_calls", None) or []:
        try:
            arguments = json.loads(call.function.arguments or "{}")
        except (json.JSONDecodeError, TypeError):
            arguments = {}
        tool_calls.append(
            ToolCall(
                id=call.id,
                name=call.function.name,
                arguments=arguments,
            )
        )
    content = message.content or ""
    cost = calculate_cost(model, usage.input_tokens, usage.output_tokens)
    return LLMTurn(
        content=content,
        tool_calls=tool_calls,
        usage=usage,
        cost_usd=cost,
        finish_reason=getattr(choice, "finish_reason", None) or "stop",
        model=model,
        reasoning_text=getattr(message, "reasoning_content", None),
    )


def _map_error(err: Exception) -> LLMError:
    """Map LiteLLM/provider exceptions into our typed error hierarchy."""
    import litellm

    message = str(err)
    if isinstance(err, litellm.ContextWindowExceededError):
        return LLMContextTooLong(message)
    if isinstance(err, litellm.RateLimitError):
        return LLMRateLimit(message)
    if isinstance(err, litellm.Timeout):
        return LLMTimeout(message)
    if isinstance(err, litellm.BadRequestError):
        return LLMBadRequest(message)
    return LLMError(message, retryable=True)
