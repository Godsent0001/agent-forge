"""LLM adapter v2 integrating LiteLLM / provider models with retries and typed errors."""
import asyncio
import json
from typing import Any

from .pricing import calculate_cost
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
            # We import litellm dynamically if present
            import litellm

            litellm.drop_params = True

            kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "timeout": params.timeout_s,
            }
            if tools_formatted:
                kwargs["tools"] = tools_formatted
            if params.temperature is not None:
                kwargs["temperature"] = params.temperature
            if params.max_tokens is not None:
                kwargs["max_tokens"] = params.max_tokens

            response = await litellm.acompletion(**kwargs)
            return _parse_response(response, model)

        except Exception as err:
            attempt += 1
            err_str = str(err).lower()

            if "context_length_exceeded" in err_str or "maximum context length" in err_str:
                raise LLMContextTooLong(f"Context window exceeded for {model}: {err}") from err
            elif "rate_limit" in err_str or "429" in err_str:
                if attempt >= max_retries:
                    raise LLMRateLimit(f"Rate limit exceeded after {attempt} retries: {err}") from err
                await asyncio.sleep(2**attempt)
            elif "timeout" in err_str or "timed out" in err_str:
                if attempt >= max_retries:
                    raise LLMTimeout(f"LLM request timed out after {attempt} retries: {err}") from err
                await asyncio.sleep(1)
            elif "invalid_request" in err_str or "400" in err_str:
                raise LLMBadRequest(f"Bad request to LLM provider: {err}") from err
            else:
                if attempt >= max_retries:
                    raise LLMError(f"LLM completion failed: {err}") from err
                await asyncio.sleep(1)


def _parse_response(response: Any, model: str) -> LLMTurn:
    choice = response.choices[0]
    message_obj = choice.message
    content = getattr(message_obj, "content", None)
    tool_calls_raw = getattr(message_obj, "tool_calls", None) or []

    parsed_tool_calls: list[ToolCall] = []
    for tc in tool_calls_raw:
        call_id = getattr(tc, "id", f"call_{len(parsed_tool_calls)}")
        fn = getattr(tc, "function", None)
        fn_name = getattr(fn, "name", "") if fn else ""
        args_raw = getattr(fn, "arguments", "{}") if fn else "{}"

        args_dict = {}
        args_err = None
        if isinstance(args_raw, str):
            try:
                args_dict = json.loads(args_raw)
            except Exception as e:
                args_err = f"Invalid JSON in arguments: {e}"
        elif isinstance(args_raw, dict):
            args_dict = args_raw

        parsed_tool_calls.append(
            ToolCall(
                id=call_id,
                name=fn_name,
                arguments=args_dict,
                arguments_error=args_err,
            )
        )

    raw_usage = getattr(response, "usage", None)
    usage = Usage()
    if raw_usage:
        usage.input_tokens = getattr(raw_usage, "prompt_tokens", 0) or 0
        usage.output_tokens = getattr(raw_usage, "completion_tokens", 0) or 0
        prompt_details = getattr(raw_usage, "prompt_tokens_details", None)
        if prompt_details:
            usage.cache_read_tokens = getattr(prompt_details, "cached_tokens", 0) or 0

    cost = calculate_cost(model, usage)

    msg_dict = {
        "role": getattr(message_obj, "role", "assistant"),
        "content": content,
    }
    if tool_calls_raw:
        msg_dict["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in tool_calls_raw
        ]

    finish_reason = getattr(choice, "finish_reason", "stop") or "stop"
    reasoning_text = getattr(message_obj, "reasoning_content", None)

    return LLMTurn(
        message=msg_dict,
        text=content,
        tool_calls=parsed_tool_calls,
        usage=usage,
        cost_usd=cost,
        finish_reason=finish_reason,
        model=model,
        reasoning_text=reasoning_text,
    )
