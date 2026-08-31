"""
LLM interface. Agents call `llm.reason(...)`, never a provider SDK directly —
this is the seam LiteLLM plugs into, per the architecture decision to keep
provider-switching out of the agent/runtime logic entirely.

This sandbox has no network access, so LiteLLM calls can't be exercised
here. The interface is written against real LiteLLM's completion() shape;
swap USE_MOCK to False once running with real API keys.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

USE_MOCK = True  # flip off once you have real provider credentials configured


@dataclass
class ToolSpec:
    name: str
    description: str


@dataclass
class LLMDecision:
    action: str  # "tool_call" | "final_answer"
    tool_name: str | None = None
    tool_input: str | None = None
    answer: str | None = None


class LLMInterface:
    def __init__(self, provider: str, model: str):
        self.provider = provider
        self.model = model

    async def reason(self, messages: list[str], tools: list[ToolSpec]) -> LLMDecision:
        if USE_MOCK:
            return await self._mock_reason(messages, tools)
        return await self._litellm_reason(messages, tools)

    async def _litellm_reason(self, messages: list[str], tools: list[ToolSpec]) -> LLMDecision:
        import litellm  # imported lazily so the mock path never needs it installed

        tool_defs = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": {
                        "type": "object",
                        "properties": {"input": {"type": "string"}},
                        "required": ["input"],
                    },
                },
            }
            for t in tools
        ]

        response = await litellm.acompletion(
            model=f"{self.provider}/{self.model}",
            messages=[{"role": "user", "content": "\n\n".join(messages)}],
            tools=tool_defs or None,
        )
        choice = response.choices[0].message

        if getattr(choice, "tool_calls", None):
            call = choice.tool_calls[0]
            args = json.loads(call.function.arguments)
            return LLMDecision(action="tool_call", tool_name=call.function.name, tool_input=args.get("input", ""))

        return LLMDecision(action="final_answer", answer=choice.content or "")

    async def _mock_reason(self, messages: list[str], tools: list[ToolSpec]) -> LLMDecision:
        """
        Deterministic stand-in: if a tool hasn't been called yet this turn
        and tools are available, call the first one; otherwise answer.
        Good enough to prove the plumbing without a real model.
        """
        already_used_tool = any(m.startswith("[TOOL RESULT") for m in messages)
        if tools and not already_used_tool:
            tool = tools[0]
            task_line = next((m for m in messages if m.startswith("[PARENT PROMPT]")), "")
            return LLMDecision(action="tool_call", tool_name=tool.name, tool_input=task_line)
        return LLMDecision(action="final_answer", answer="(mock) Task considered complete.")
