from app.contracts.naming import canonical_tool_names, dedupe_names, sanitize_tool_name


def test_model_visible_tool_names_are_valid_even_when_display_names_are_not():
    names = canonical_tool_names(["Web Search", "Browser (public)", "web_search"])
    assert names == ["web_search", "browser__public_", "web_search_2"]
    assert all(name[0].islower() and " " not in name and "(" not in name for name in names)


def test_tool_names_are_sanitized_and_deduplicated_deterministically():
    names = [sanitize_tool_name(value) for value in ("Web Search", "web search", "web_search")]
    assert dedupe_names(names) == ["web_search", "web_search_2", "web_search_3"]



def test_general_shell_and_browser_tools_are_registered():
    from app.tools.registry import build_tool, known_tool_kinds

    assert {"shell", "browser", "web_search", "workspace_files"} <= known_tool_kinds()
    assert build_tool("shell", {}).name == "shell"
    assert build_tool("browser", {}).name == "browser"



def test_python_uses_the_shared_runtime_without_environment_management():
    from app.contracts.graph import ToolBinding
    from app.tools.catalog import CATALOG
    from app.tools.python_project import PythonProjectTool
    from app.tools.registry import DefaultToolFactory, known_tool_kinds

    assert "python_environment" not in known_tool_kinds()
    assert not any(entry.kind == "python_environment" for entry in CATALOG)
    assert any(entry.kind == "python" and entry.name == "Python" for entry in CATALOG)

    binding = ToolBinding(id="python", kind="python", name="python", description="")
    python_tool = DefaultToolFactory().build(binding)
    assert isinstance(python_tool, PythonProjectTool)


def test_tool_schema_uses_a_valid_identifier_for_display_name():
    from app.contracts.graph import ToolBinding
    from app.tools.registry import DefaultToolFactory
    from app.tools.specs import tool_spec

    binding = ToolBinding(
        id="web-search-id",
        kind="web_search",
        name="Web Search (free)",
        description="Search the public web",
    )
    tool = DefaultToolFactory().build(binding)
    schema = tool_spec(binding, tool)
    assert schema.name == "web_search__free_"
    assert " " not in schema.name
    assert "(" not in schema.name and ")" not in schema.name


def test_browser_and_web_search_have_provider_safe_names_and_string_input_schemas():
    from app.contracts.graph import ToolBinding
    from app.contracts.naming import sanitize_tool_name
    from app.tools.registry import DefaultToolFactory
    from app.tools.specs import tool_spec

    for kind, display_name in (("browser", "Browser Tool"), ("web_search", "Web Search")):
        binding = ToolBinding(id=f"{kind}-binding", kind=kind, name=display_name)
        schema = tool_spec(binding, DefaultToolFactory().build(binding))
        assert schema.name == sanitize_tool_name(display_name)
        assert schema.parameters["type"] == "object"
        assert schema.parameters["properties"]["input"]["type"] == "string"
