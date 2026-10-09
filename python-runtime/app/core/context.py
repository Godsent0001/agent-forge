"""Context compilation for bounded, artifact-backed model prompts.

The execution transcript remains authoritative in RunnerCore/checkpoints. This module
creates a disposable prompt view: it compacts old tool payloads into claim-check
references without mutating the transcript or breaking tool-call/result pairing.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

DEFAULT_CONTEXT_CHAR_BUDGET = 48_000
DEFAULT_RECENT_TOOL_RESULTS = 4
TOOL_RESULT_COMPACT_THRESHOLD = 1_000


@dataclass(frozen=True)
class ContextCompileStats:
    original_chars: int
    compiled_chars: int
    compacted_tool_results: int
    compacted_messages: int

    @property
    def estimated_tokens_saved(self) -> int:
        return max(0, self.original_chars - self.compiled_chars) // 4


class ContextCompiler:
    """Compile the full transcript into a bounded prompt view.

    This is deliberately deterministic and model-independent. The latest user task,
    system prompt, assistant tool-call envelopes, and recent tool results are protected.
    Older tool results are saved as workspace artifacts and replaced with references.
    """

    def __init__(
        self,
        *,
        max_context_chars: int = DEFAULT_CONTEXT_CHAR_BUDGET,
        recent_tool_results: int = DEFAULT_RECENT_TOOL_RESULTS,
        compact_threshold: int = TOOL_RESULT_COMPACT_THRESHOLD,
    ) -> None:
        self.max_context_chars = max(4_000, int(max_context_chars))
        self.recent_tool_results = max(0, int(recent_tool_results))
        self.compact_threshold = max(256, int(compact_threshold))

    @staticmethod
    def bound_block(text: str, max_chars: int, label: str) -> str:
        """Bound auxiliary prompt sections while preserving their identity."""
        if len(text) <= max_chars:
            return text
        omitted = len(text) - max_chars
        return text[:max_chars] + f" [{label} compacted; {omitted} characters omitted]"

    def compile(self, messages: list[dict[str, Any]], workspace: Any) -> tuple[list[dict[str, Any]], ContextCompileStats]:
        compiled = copy.deepcopy(messages)
        original_chars = self._size(compiled)
        tool_indices = [i for i, m in enumerate(compiled) if m.get("role") == "tool"]
        protected_tool_indices = set(tool_indices[-self.recent_tool_results:]) if self.recent_tool_results else set()
        compacted_tools = 0
        compacted_messages = 0

        # Older large tool payloads are always claim-checked. They remain available
        # in .results/<tool_call_id>.txt and can be retrieved by a later tool call.
        for index in tool_indices:
            message = compiled[index]
            content = message.get("content", "")
            if index in protected_tool_indices or not isinstance(content, str):
                continue
            if len(content) <= self.compact_threshold:
                continue
            message["content"] = self._artifact_pointer(message, content, workspace)
            compacted_tools += 1

        # If the prompt is still over budget, compact oldest eligible content first.
        # Never remove messages: tool-call IDs and their corresponding tool messages
        # must remain present for providers that validate the conversation protocol.
        if self._size(compiled) > self.max_context_chars:
            for index in tool_indices:
                if self._size(compiled) <= self.max_context_chars:
                    break
                message = compiled[index]
                content = message.get("content", "")
                if index in protected_tool_indices or not isinstance(content, str):
                    continue
                if len(content) <= 256:
                    continue
                message["content"] = self._artifact_pointer(message, content, workspace)
                compacted_tools += 1

        if self._size(compiled) > self.max_context_chars:
            last_user = max(
                (i for i, message in enumerate(compiled) if message.get("role") == "user"),
                default=-1,
            )
            for index, message in enumerate(compiled):
                if self._size(compiled) <= self.max_context_chars:
                    break
                if index == 0 or index == last_user or message.get("role") == "system":
                    continue
                if message.get("tool_calls") or message.get("role") == "tool":
                    continue
                content = message.get("content")
                if not isinstance(content, str) or len(content) <= 512:
                    continue
                keep = max(256, min(800, self.max_context_chars // 30))
                head = keep // 2
                tail = keep - head
                message["content"] = (
                    content[:head]
                    + f" [older message compacted; {len(content) - keep} characters omitted] "
                    + content[-tail:]
                )
                compacted_messages += 1

        return compiled, ContextCompileStats(
            original_chars=original_chars,
            compiled_chars=self._size(compiled),
            compacted_tool_results=compacted_tools,
            compacted_messages=compacted_messages,
        )

    @staticmethod
    def _artifact_pointer(message: dict[str, Any], content: str, workspace: Any) -> str:
        call_id = str(message.get("tool_call_id") or "unknown-tool-result")
        artifact_path: str | None = None
        writer = getattr(workspace, "write_result", None)
        if callable(writer) and call_id != "unknown-tool-result":
            try:
                artifact = writer(call_id, content)
                artifact_path = getattr(artifact, "path", None)
                if artifact_path is None and isinstance(artifact, dict):
                    artifact_path = artifact.get("path")
            except Exception:
                artifact_path = None

        excerpt = content[:240].replace("\x00", "")
        if len(content) > 240:
            excerpt += "…"
        if artifact_path:
            return (
                f"[Earlier tool result compacted. Full result saved at {artifact_path}. "
                f"Retrieve that artifact only if needed.]\nExcerpt: {excerpt}"
            )
        return f"[Earlier tool result compacted; full result unavailable as an artifact.]\nExcerpt: {excerpt}"

    @staticmethod
    def _size(messages: list[dict[str, Any]]) -> int:
        total = 0
        for message in messages:
            try:
                total += len(str(message.get("content", "")))
                total += len(str(message.get("tool_calls", "")))
            except Exception:
                total += 128
        return total
