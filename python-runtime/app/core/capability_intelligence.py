"""Compact, run-specific self-awareness derived from the live tool registry.

The model already receives full JSON schemas through the tool-calling API. This
manifest intentionally avoids duplicating those schemas or dumping source/docs
into the prompt.
"""
from __future__ import annotations

from collections.abc import Sequence

from app.core.llm.types import ToolSpec

_MAX_MANIFEST_CHARS = 2400
_MAX_DESCRIPTION_CHARS = 96


def build_runtime_capability_manifest(
    tools: Sequence[ToolSpec],
    workspace_root: str,
) -> str:
    """Describe only the capabilities and workspace that are real for this run."""
    lines = [
        "AgentForge runtime self-awareness (current run)",
        "- Execution uses the shared RunnerCore; the tools declared for this request are authoritative.",
        "- Select tools by task intent. Their live API schemas are supplied separately; follow those exact names, fields, and required arguments.",
        "- A tool omitted from this run's declarations is not available to this run. Do not invent tools, parameters, access, or completed actions.",
        f"- Persistent project workspace: {workspace_root}",
        "- Conversation messages supplied in this request are conversation history; semantic memory is separate and only available when explicitly provided or through a declared memory tool.",
    ]
    if tools:
        lines.append("- Tools available in this run:")
        lines.extend(
            f"  - {tool.name}: {' '.join((tool.description or 'No description provided.').split())[:_MAX_DESCRIPTION_CHARS]}"
            for tool in tools
        )
    else:
        lines.append("- No tool calls are available in this run; answer from supplied context or explain the limitation.")

    manifest = "\n".join(lines)
    if len(manifest) <= _MAX_MANIFEST_CHARS:
        return manifest

    # Keep every actual tool name visible, trimming descriptive prose before
    # dropping any capabilities. Full schemas remain available to the model.
    compact_lines = lines[:5]
    if tools:
        compact_lines.append("- Tools available in this run:")
        compact_lines.extend(f"  - {tool.name}" for tool in tools)
    else:
        compact_lines.append("- No tool calls are available in this run.")
    compact = "\n".join(compact_lines)
    if len(compact) <= _MAX_MANIFEST_CHARS:
        return compact

    # Extremely large custom-tool catalogs still stay bounded; preserve all names
    # when possible and make the omission explicit rather than implying completeness.
    names = [tool.name for tool in tools]
    prefix = "\n".join(lines[:5] + ["- Available tool names:"])
    budget = max(0, _MAX_MANIFEST_CHARS - len(prefix) - 32)
    selected: list[str] = []
    used = 0
    for name in names:
        addition = len(name) + (2 if selected else 0)
        if used + addition > budget:
            break
        selected.append(name)
        used += addition
    suffix = "" if len(selected) == len(names) else f" … (+{len(names) - len(selected)} more registered tools)"
    return prefix + "\n  " + ", ".join(selected) + suffix
