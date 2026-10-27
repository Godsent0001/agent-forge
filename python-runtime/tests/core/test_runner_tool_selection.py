from app.core.llm.types import ToolSpec
from app.core.runner import _restrict_tools_for_explicit_request


def _tool(name: str) -> ToolSpec:
    return ToolSpec(name=name, description=f"{name} tool", parameters={"type": "object"})


def test_explicit_search_tool_request_excludes_shell_substitution():
    tools = [_tool("shell"), _tool("web_search"), _tool("browser")]

    selected, requested = _restrict_tools_for_explicit_request(
        "Please test the search tool; do not use CMD.", tools
    )

    assert requested == "search"
    assert [tool.name for tool in selected] == ["web_search"]


def test_explicit_shell_request_selects_shell_tool():
    tools = [_tool("shell"), _tool("web_search"), _tool("browser")]

    selected, requested = _restrict_tools_for_explicit_request(
        "Use the shell tool to create a folder.", tools
    )

    assert requested == "shell"
    assert [tool.name for tool in selected] == ["shell"]


def test_unrequested_tool_selection_is_unchanged():
    tools = [_tool("shell"), _tool("web_search")]

    selected, requested = _restrict_tools_for_explicit_request(
        "Create a calculator app.", tools
    )

    assert requested is None
    assert selected == tools


def test_missing_explicitly_requested_tool_does_not_enable_substitutes():
    tools = [_tool("shell"), _tool("browser")]

    selected, requested = _restrict_tools_for_explicit_request(
        "Use the search tool.", tools
    )

    assert requested == "search"
    assert selected == []
