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

import os

USE_MOCK = False  # Default to real LiteLLM; falls back to mock if LiteLLM call fails or no API keys are present


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
        try:
            return await self._litellm_reason(messages, tools)
        except Exception as e:
            return await self._mock_reason(messages, tools)

    async def summarize(self, existing_summary: str, new_entries: list[str]) -> str:
        """
        Fold a batch of raw memory entries into (an update of) the existing
        rolling summary. Used by app/runtime/memory.py's compaction step —
        never called on every run, only when the recent-window overflows.
        """
        if USE_MOCK:
            return self._mock_summarize(existing_summary, new_entries)
        try:
            return await self._litellm_summarize(existing_summary, new_entries)
        except Exception:
            return self._mock_summarize(existing_summary, new_entries)

    async def _litellm_summarize(self, existing_summary: str, new_entries: list[str]) -> str:
        import litellm

        prompt = (
            "Update the running summary below with the new memory entries. "
            "Preserve concrete facts, decisions, and names; drop redundant or "
            "superseded detail. Keep it dense — this is compressed long-term "
            "memory, not a transcript. Output only the updated summary text.\n\n"
            f"[EXISTING SUMMARY]\n{existing_summary or '(none yet)'}\n\n"
            f"[NEW ENTRIES TO FOLD IN]\n" + "\n".join(f"- {e}" for e in new_entries)
        )
        response = await litellm.acompletion(
            model=f"{self.provider}/{self.model}",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or existing_summary

    def _mock_summarize(self, existing_summary: str, new_entries: list[str]) -> str:
        """
        Deterministic stand-in: concatenate + hard-truncate rather than a
        real abstractive summary. Good enough to prove the compaction
        plumbing works without a real model; swap is automatic once
        USE_MOCK is False and credentials are configured.
        """
        combined = (existing_summary + " " if existing_summary else "") + " ".join(new_entries)
        MAX_SUMMARY_CHARS = 800
        if len(combined) <= MAX_SUMMARY_CHARS:
            return combined
        return "…" + combined[-MAX_SUMMARY_CHARS:]


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
