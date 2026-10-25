from app.contracts.naming import dedupe_names, sanitize_tool_name


def test_tool_names_are_sanitized_and_deduplicated_deterministically():
    names = [sanitize_tool_name(value) for value in ("Web Search", "web search", "web_search")]
    assert dedupe_names(names) == ["web_search", "web_search_2", "web_search_3"]

