from app.contracts.graph import ToolBinding
from app.contracts.naming import dedupe_names, sanitize_tool_name
from app.services.core_adapters import LegacyToolAdapter


def test_tool_names_are_sanitized_and_deduplicated_deterministically():
    names = [sanitize_tool_name(value) for value in ("Web Search", "web search", "web_search")]
    assert dedupe_names(names) == ["web_search", "web_search_2", "web_search_3"]


def test_legacy_adapter_preserves_the_graph_binding_name():
    adapter = LegacyToolAdapter(ToolBinding(
        id="tool-1", kind="python", name="python_for_research",
        description="Execute a bounded Python snippet", config={},
    ))
    assert adapter.name == "python_for_research"
