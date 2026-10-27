from app.contracts.naming import dedupe_names, sanitize_tool_name


def test_tool_names_are_sanitized_and_deduplicated_deterministically():
    names = [sanitize_tool_name(value) for value in ("Web Search", "web search", "web_search")]
    assert dedupe_names(names) == ["web_search", "web_search_2", "web_search_3"]



def test_general_shell_and_browser_tools_are_registered():
    from app.tools.registry import build_tool, known_tool_kinds

    assert {"shell", "browser", "web_search"} <= known_tool_kinds()
    assert build_tool("shell", {}).name == "shell"
    assert build_tool("browser", {}).name == "browser"
