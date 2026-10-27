"""Resolve explicit tool constraints against the tools actually available to an agent.

This is catalog-driven: it does not hard-code tool names or assume that a particular
capability is implemented by a particular tool.
"""
from __future__ import annotations

import re

from app.core.llm.types import ToolSpec


_REQUIRED_TOOL = re.compile(
    r"\b(?:use|call|invoke|test|try|run|execute)\s+"
    r"(?:(?:the|a|an)\s+)?"
    r"(?P<alias>[a-z][a-z0-9 _-]{0,39}?)\s+(?:tool|command)\b",
    re.IGNORECASE,
)
_FORBIDDEN_TOOL = re.compile(
    r"\b(?:do not|don't|never|avoid)\s+(?:use|call|run|invoke)\s+"
    r"(?:(?:the|a|an)\s+)?(?P<alias>[a-z][a-z0-9_-]{0,30})\b",
    re.IGNORECASE,
)
_STOP_WORDS = {"a", "an", "the", "my", "your", "its", "our", "their", "tool", "command", "system", "agentforge", "please", "only"}


def _tokens(value: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", value.casefold()) if word not in _STOP_WORDS}


def _tool_terms(tool: ToolSpec) -> set[str]:
    terms = _tokens(tool.name.replace("_", " "))
    # Add only distinctive aliases from descriptions (acronyms and CamelCase
    # names), avoiding generic description words that would match unrelated tools.
    for alias in re.findall(r"\b[A-Z]{2,}\b|\b[A-Z][a-z]+[A-Z][A-Za-z]*\b", tool.description):
        terms.update(_tokens(alias))
    return terms


def _matches_alias(alias: str, tool: ToolSpec) -> bool:
    requested = _tokens(alias)
    return bool(requested) and requested.issubset(_tool_terms(tool))


def constrain_tools_for_task(task: str, tools: list[ToolSpec]) -> tuple[list[ToolSpec], str | None]:
    """Honor explicit required/forbidden tool mentions using the live tool catalog.

    If the task requires a capability that is not available, return no tools and
    the requested label so the caller can explain the limitation rather than
    silently substituting an unrelated capability.
    """
    required = _REQUIRED_TOOL.search(task)
    forbidden_aliases = [match.group("alias").strip() for match in _FORBIDDEN_TOOL.finditer(task)]

    if required:
        requested = required.group("alias").strip()
        matches = [tool for tool in tools if _matches_alias(requested, tool)]
        if not matches:
            return [], requested
        allowed = [
            tool for tool in matches
            if not any(_matches_alias(alias, tool) for alias in forbidden_aliases)
        ]
        return allowed, requested

    if forbidden_aliases:
        tools = [
            tool for tool in tools
            if not any(_matches_alias(alias, tool) for alias in forbidden_aliases)
        ]
    return tools, None
