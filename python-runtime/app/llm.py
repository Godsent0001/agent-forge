"""
LLM interface. Agents call `llm.reason(...)`, never a provider SDK directly —
this is the seam LiteLLM plugs into, keeping provider-switching
out of the agent/runtime logic entirely.
"""

from __future__ import annotations

import json
import os
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("agentforge.llm")

USE_MOCK = False  # Default to real LLM calls; falls back to mock if LiteLLM call fails or no API keys are present


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

    def _format_model_name(self) -> str:
        provider = (self.provider or "").strip().lower()
        model = (self.model or "").strip()

        # Handle Gemini / Google model variants
        if "gemini" in provider or "gemini" in model.lower() or "google" in provider:
            cleaned_model = model
            if cleaned_model.startswith("models/"):
                cleaned_model = cleaned_model[len("models/"):]
            if cleaned_model.startswith("gemini/"):
                cleaned_model = cleaned_model[len("gemini/"):]
            if cleaned_model.startswith("google/"):
                cleaned_model = cleaned_model[len("google/"):]
            return f"gemini/{cleaned_model}"

        if provider and not model.startswith(f"{provider}/"):
            return f"{provider}/{model}"
        return model

    async def reason(self, messages: list[str], tools: list[ToolSpec]) -> LLMDecision:
        if USE_MOCK:
            logger.info("USE_MOCK is True; using mock reasoner")
            return await self._mock_reason(messages, tools)
        try:
            return await self._litellm_reason(messages, tools)
        except Exception as e:
            logger.exception(f"LiteLLM reasoning error for provider={self.provider}, model={self.model}: {e}")
            raise RuntimeError(f"LLM Reasoning Error ({self.provider}/{self.model}): {e}") from e

    async def summarize(self, existing_summary: str, new_entries: list[str]) -> str:
        """
        Fold a batch of raw memory entries into an update of existing summary.
        """
        if USE_MOCK:
            return self._mock_summarize(existing_summary, new_entries)
        try:
            return await self._litellm_summarize(existing_summary, new_entries)
        except Exception as e:
            logger.exception(f"LiteLLM summarize error: {e}")
            return self._mock_summarize(existing_summary, new_entries)

    async def _litellm_summarize(self, existing_summary: str, new_entries: list[str]) -> str:
        import litellm

        formatted_model = self._format_model_name()
        prompt = (
            "Update the running summary below with the new memory entries. "
            "Preserve concrete facts, decisions, and names; drop redundant or "
            "superseded detail. Keep it dense — this is compressed long-term "
            "memory, not a transcript. Output only the updated summary text.\n\n"
            f"[EXISTING SUMMARY]\n{existing_summary or '(none yet)'}\n\n"
            f"[NEW ENTRIES TO FOLD IN]\n" + "\n".join(f"- {e}" for e in new_entries)
        )
        gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if gemini_key:
            os.environ["GEMINI_API_KEY"] = gemini_key
            os.environ["GOOGLE_API_KEY"] = gemini_key

        kwargs: dict[str, Any] = {
            "model": formatted_model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if gemini_key and formatted_model.startswith("gemini/"):
            kwargs["api_key"] = gemini_key

        response = await litellm.acompletion(**kwargs)
        return response.choices[0].message.content or existing_summary

    def _mock_summarize(self, existing_summary: str, new_entries: list[str]) -> str:
        combined = (existing_summary + " " if existing_summary else "") + " ".join(new_entries)
        MAX_SUMMARY_CHARS = 800
        if len(combined) <= MAX_SUMMARY_CHARS:
            return combined
        return "…" + combined[-MAX_SUMMARY_CHARS:]

    def _build_messages_payload(self, messages: list[str]) -> list[dict[str, Any]]:
        formatted_messages: list[dict[str, Any]] = []

        for m in messages:
            if m.startswith("[TOOL RESULT: "):
                header_end = m.find("]")
                tool_header = m[len("[TOOL RESULT: "):header_end] if header_end != -1 else "tool"
                tool_name = tool_header.split("]")[0].strip()
                content = m[header_end + 1:].strip() if header_end != -1 else m

                formatted_messages.append({
                    "role": "assistant",
                    "content": f"Using tool {tool_name}...",
                    "tool_calls": [{
                        "id": f"call_{tool_name}",
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps({"input": "previous_step"})
                        }
                    }]
                })

                formatted_messages.append({
                    "role": "tool",
                    "tool_call_id": f"call_{tool_name}",
                    "name": tool_name,
                    "content": content,
                })
            else:
                formatted_messages.append({"role": "user", "content": m})

        return formatted_messages

    async def _litellm_reason(self, messages: list[str], tools: list[ToolSpec]) -> LLMDecision:
        import litellm

        formatted_model = self._format_model_name()

        # Debug key existence
        has_gemini = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
        has_openai = bool(os.environ.get("OPENAI_API_KEY"))
        has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
        logger.info(
            f"Reasoning call for model='{formatted_model}' (provider='{self.provider}', model='{self.model}'). "
            f"API Keys available: gemini={has_gemini}, openai={has_openai}, anthropic={has_anthropic}"
        )

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

        formatted_messages = self._build_messages_payload(messages)

        logger.debug(f"Sending to litellm: messages_count={len(formatted_messages)}, tools_count={len(tool_defs)}")

        # Ensure GEMINI_API_KEY and GOOGLE_API_KEY are synchronized if either is present
        gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if gemini_key:
            os.environ["GEMINI_API_KEY"] = gemini_key
            os.environ["GOOGLE_API_KEY"] = gemini_key

        kwargs: dict[str, Any] = {
            "model": formatted_model,
            "messages": formatted_messages,
            "tools": tool_defs or None,
        }
        if gemini_key and formatted_model.startswith("gemini/"):
            kwargs["api_key"] = gemini_key

        response = await litellm.acompletion(**kwargs)
        choice = response.choices[0].message

        tool_calls = getattr(choice, "tool_calls", None)
        if tool_calls:
            call = tool_calls[0]
            args_str = call.function.arguments if hasattr(call.function, "arguments") else "{}"
            if isinstance(args_str, str):
                try:
                    args = json.loads(args_str)
                except Exception:
                    args = {"input": args_str}
            elif isinstance(args_str, dict):
                args = args_str
            else:
                args = {}

            tool_input = args.get("input", "") if isinstance(args, dict) else str(args)
            logger.info(f"LLM decided tool_call: tool_name='{call.function.name}', tool_input='{tool_input}'")
            return LLMDecision(action="tool_call", tool_name=call.function.name, tool_input=tool_input)

        logger.info("LLM decided final_answer")
        return LLMDecision(action="final_answer", answer=choice.content or "")

    async def _mock_reason(self, messages: list[str], tools: list[ToolSpec]) -> LLMDecision:
        already_used_tool = any(m.startswith("[TOOL RESULT") for m in messages)
        if tools and not already_used_tool:
            tool = tools[0]
            task_line = next((m for m in messages if m.startswith("[PARENT PROMPT]")), "")
            return LLMDecision(action="tool_call", tool_name=tool.name, tool_input=task_line)
        return LLMDecision(action="final_answer", answer="(mock) Task considered complete.")
