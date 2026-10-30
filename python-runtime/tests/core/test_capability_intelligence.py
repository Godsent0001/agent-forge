from app.core.capability_intelligence import build_runtime_capability_manifest
from app.core.llm.types import ToolSpec


def test_manifest_describes_only_live_tools_and_workspace_without_duplicating_schemas():
    tools = [
        ToolSpec(
            name="web_search",
            description="Search the public web and return source links.",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        ),
        ToolSpec(
            name="python",
            description="Execute Python and manage the shared project environment.",
            parameters={"type": "object", "properties": {"action": {"type": "string"}}},
        ),
    ]

    manifest = build_runtime_capability_manifest(tools, "C:/AgentForge/workspace")

    assert "C:/AgentForge/workspace" in manifest
    assert "web_search: Search the public web" in manifest
    assert "python: Execute Python" in manifest
    assert "schema" in manifest
    assert "properties" not in manifest
    assert "python_environment" not in manifest


def test_manifest_says_when_no_tools_are_available():
    manifest = build_runtime_capability_manifest([], "/workspace")

    assert "No tool calls are available in this run" in manifest
    assert "/workspace" in manifest


def test_manifest_stays_bounded_for_large_custom_tool_catalogs():
    tools = [
        ToolSpec(
            name=f"custom_tool_{index}",
            description="A long custom tool description " * 12,
            parameters={"type": "object", "properties": {"value": {"type": "string"}}},
        )
        for index in range(80)
    ]

    manifest = build_runtime_capability_manifest(tools, "/workspace")

    assert len(manifest) <= 1800
    assert "Available tool names" in manifest or "Tools available in this run" in manifest
    assert "custom_tool_0" in manifest
