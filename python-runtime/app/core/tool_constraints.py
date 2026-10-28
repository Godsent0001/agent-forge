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
    r"(?P<alias>[a-z][a-z0-9 _-]{0,39}?)\s+(?:tool|command)s?\b",
    re.IGNORECASE,
)
_RELATED_TOOL = re.compile(
    r"\b(?:and|or)\s+(?:(?:the|a|an)\s+)?"
    r"(?P<alias>[a-z][a-z0-9 _-]{0,39}?)\s+(?:tool|command)s?\b",
    re.IGNORECASE,
)
_FORBIDDEN_TOOL = re.compile(
    r"\b(?:do not|don't|never|avoid)\s+(?:use|call|run|invoke)\s+"
    r"(?:(?:the|a|an)\s+)?(?P<alias>[a-z][a-z0-9_-]{0,30})\b",
    re.IGNORECASE,
)
_STOP_WORDS = {
    "a", "an", "the", "my", "your", "its", "our", "their", "it",
    "tool", "tools", "command", "commands", "system", "agentforge",
    "please", "only",
}


def _tokens(value: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z0-9]+", value.casefold())
        if word not in _STOP_WORDS
    }


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


def _normalize_alias(alias: str) -> str:
    return re.sub(
        r"^(?:(?:the|a|an|my|your|its|our|their|it)\s+)+",
        "",
        alias.strip(),
        flags=re.IGNORECASE,
    ).strip()


def constrain_tools_for_task(
    task: str, tools: list[ToolSpec]
) -> tuple[list[ToolSpec], str | None]:
    """Honor explicit required/forbidden tool mentions using the live tool catalog.

    Multiple explicitly requested tools are retained together for multi-step tasks.
    If any required capability is unavailable, no unrelated tool is exposed as a
    substitute; the caller can explain the missing capability.
    """
    required_matches = list(_REQUIRED_TOOL.finditer(task))
    required_aliases: list[str] = []
    if required_matches:
        first = required_matches[0]
        required_aliases.append(_normalize_alias(first.group("alias")))
        # Support natural compound requests such as "use the search tool and shell
        # tool" without treating every incidental tool mention as a hard constraint.
        clause_end = re.search(r"[.!?;\n]", task[first.end():])
        end = first.end() + clause_end.start() if clause_end else len(task)
        for match in _RELATED_TOOL.finditer(task, first.end(), end):
            required_aliases.append(_normalize_alias(match.group("alias")))
    required_aliases = list(dict.fromkeys(alias for alias in required_aliases if alias))

    forbidden_aliases = [
        _normalize_alias(match.group("alias"))
        for match in _FORBIDDEN_TOOL.finditer(task)
    ]

    if required_aliases:
        matched_tools: dict[str, ToolSpec] = {}
        missing_aliases: list[str] = []
        for alias in required_aliases:
            matches = [tool for tool in tools if _matches_alias(alias, tool)]
            # Prefer an exact canonical tool name when one exists. Without this,
            # asking for "python" also matches "python_environment" because the
            # token matcher sees only the shared word and exposes both interfaces.
            normalized_alias = " ".join(alias.casefold().replace("_", " ").replace("-", " ").split())
            exact_matches = [
                tool for tool in matches
                if " ".join(tool.name.casefold().replace("_", " ").replace("-", " ").split()) == normalized_alias
            ]
            if exact_matches:
                matches = exact_matches
            if not matches:
                missing_aliases.append(alias)
                continue
            for tool in matches:
                matched_tools[tool.name] = tool

        allowed = [
            tool
            for tool in matched_tools.values()
            if not any(_matches_alias(alias, tool) for alias in forbidden_aliases)
        ]
        if missing_aliases:
            # Continue with explicitly requested capabilities that are available;
            # report missing capabilities rather than silently substituting tools.
            return allowed, f"missing capability: {', '.join(missing_aliases)}"
        if not allowed:
            return [], ", ".join(required_aliases)
        return allowed, ", ".join(required_aliases)

    if forbidden_aliases:
        tools = [
            tool
            for tool in tools
            if not any(_matches_alias(alias, tool) for alias in forbidden_aliases)
        ]
    return tools, None
