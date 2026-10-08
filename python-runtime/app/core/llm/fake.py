"""FakeLLM implementation for offline testing and scripting."""
import asyncio
import json
from typing import Callable, Sequence

from .types import LLMTurn, ToolCall, Usage


class FakeLLM:
    """Scripted LLM stand-in for testing without live network calls."""

    def __init__(
        self,
        script: Sequence[LLMTurn | Exception | dict] | Callable[..., LLMTurn | Exception] | None = None,
        default_model: str = "fake/model",
    ):
        self.default_model = default_model
        self.received_calls: list[dict] = []
        self._script: list[LLMTurn | Exception | dict] = list(script) if isinstance(script, list | tuple) else []
        self._callable_script: Callable[..., LLMTurn | Exception] | None = (
            script if callable(script) else None
        )

    def add_turn(self, turn: LLMTurn | Exception | dict) -> None:
        self._script.append(turn)

    async def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        params: dict | None = None,
        delay_s: float = 0.0,
    ) -> LLMTurn:
        """Process a simulated completion turn."""
        call_record = {
            "messages": messages,
            "tools": tools or [],
            "params": params or {},
        }
        self.received_calls.append(call_record)

        if delay_s > 0:
            await asyncio.sleep(delay_s)

        if self._callable_script:
            res = self._callable_script(messages, tools, params)
            if isinstance(res, Exception):
                raise res
            return res

        if not self._script:
            last_msg = messages[-1]["content"] if messages and "content" in messages[-1] else ""
            return LLMTurn(
                message={"role": "assistant", "content": f"Fake response to: {last_msg}"},
                text=f"Fake response to: {last_msg}",
                usage=Usage(input_tokens=10, output_tokens=10),
                cost_usd=0.0,
                model=self.default_model,
            )

        next_item = self._script.pop(0)
        if isinstance(next_item, Exception):
            raise next_item

        if isinstance(next_item, dict):
            text = next_item.get("text")
            content = next_item.get("content", text or "")
            tool_calls = next_item.get("tool_calls", [])
            tc_objs = []
            for tc in tool_calls:
                if isinstance(tc, ToolCall):
                    tc_objs.append(tc)
                elif isinstance(tc, dict):
                    tc_objs.append(
                        ToolCall(
                            id=tc.get("id", "call_fake"),
                            name=tc["name"],
                            arguments=tc.get("arguments", {}),
                            arguments_error=tc.get("arguments_error"),
                        )
                    )

            msg_dict = {"role": "assistant", "content": content}
            if tc_objs:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments) if isinstance(tc.arguments, dict) else str(tc.arguments),
                        },
                    }
                    for tc in tc_objs
                ]

            return LLMTurn(
                message=msg_dict,
                text=text,
                tool_calls=tc_objs,
                usage=Usage(**next_item.get("usage", {"input_tokens": 10, "output_tokens": 10})),
                cost_usd=next_item.get("cost_usd", 0.0),
                finish_reason=next_item.get("finish_reason", "stop"),
                model=next_item.get("model", self.default_model),
                reasoning_text=next_item.get("reasoning_text"),
            )

        # Standard LLMTurn object
        msg_dict = dict(next_item.message) if next_item.message else {"role": "assistant", "content": next_item.text or ""}
        if next_item.tool_calls and "tool_calls" not in msg_dict:
            msg_dict["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments) if isinstance(tc.arguments, dict) else str(tc.arguments),
                    },
                }
                for tc in next_item.tool_calls
            ]
        next_item.message = msg_dict

        return next_item
