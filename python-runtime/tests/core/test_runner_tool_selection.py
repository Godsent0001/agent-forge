from app.core.llm.types import ToolSpec
from app.core.tool_constraints import constrain_tools_for_task
from app.core.runner import _safe_tool_arguments


def _tool(name: str, description: str) -> ToolSpec:
    return ToolSpec(name=name, description=description, parameters={"type": "object"})


def test_explicit_tool_constraint_uses_catalog_not_hardcoded_tool_names():
    tools = [
        _tool("web_search", "Search the web for ranked sources."),
        _tool("shell", "Run a CMD/PowerShell command in the workspace."),
        _tool("database_query", "Query the project database."),
    ]

    selected, requested = constrain_tools_for_task(
        "Please test the search tool and do not use CMD.", tools
    )

    assert requested == "search"
    assert [tool.name for tool in selected] == ["web_search"]


def test_possessive_tool_reference_matches_catalog_capability():
    tools = [
        _tool("web_search", "Search the web."),
        _tool("shell", "Run a CMD/PowerShell command."),
    ]

    selected, requested = constrain_tools_for_task(
        "Please test/use its search tool, not CMD.", tools
    )

    assert requested == "search"
    assert [tool.name for tool in selected] == ["web_search"]


def test_generic_tool_name_can_be_required():
    tools = [
        _tool("web_search", "Search the web."),
        _tool("database_query", "Query the project database."),
    ]

    selected, requested = constrain_tools_for_task("Execute the database query tool.", tools)

    assert requested == "database query"
    assert [tool.name for tool in selected] == ["database_query"]


def test_multiple_explicit_tools_remain_available_for_multi_step_task():
    tools = [
        _tool("web_search", "Search the web."),
        _tool("shell", "Run a CMD/PowerShell command."),
        _tool("file_system", "Read and write project files."),
    ]

    selected, requested = constrain_tools_for_task(
        "Use the web search tool and shell tool to find information and save a report.",
        tools,
    )

    assert requested == "web search, shell"
    assert [tool.name for tool in selected] == ["web_search", "shell"]


def test_missing_required_capability_does_not_substitute_another_tool():
    tools = [
        _tool("web_search", "Search the web."),
        _tool("shell", "Run a CMD/PowerShell command."),
    ]

    selected, requested = constrain_tools_for_task("Use the OCR tool.", tools)

    assert requested == "missing capability: OCR"
    assert selected == []


def test_missing_one_of_multiple_capabilities_preserves_available_requested_work():
    tools = [
        _tool("web_search", "Search the web."),
        _tool("shell", "Run a CMD/PowerShell command."),
    ]

    selected, requested = constrain_tools_for_task(
        "Use the web search tool and OCR tool.", tools
    )

    assert requested == "missing capability: OCR"
    assert [tool.name for tool in selected] == ["web_search"]


def test_forbidden_tool_is_removed_without_restricting_other_capabilities():
    tools = [
        _tool("shell", "Run a CMD/PowerShell command."),
        _tool("database_query", "Query the project database."),
    ]

    selected, requested = constrain_tools_for_task("Do not use CMD.", tools)

    assert requested is None
    assert [tool.name for tool in selected] == ["database_query"]


def test_exact_python_tool_request_does_not_also_select_python_environment():
    tools = [
        _tool("python", "Execute Python code snippets."),
        _tool("python_environment", "Create virtual environments and install Python packages."),
    ]
    selected, requested = constrain_tools_for_task("Use the Python tool to inspect this source.", tools)
    assert requested == "python"
    assert [tool.name for tool in selected] == ["python"]


def test_forbidding_python_does_not_accidentally_forbid_python_environment():
    tools = [
        _tool("python", "Execute Python code snippets."),
        _tool("python_environment", "Create virtual environments and install Python packages."),
        _tool("shell", "Run a CMD or PowerShell command."),
    ]
    selected, requested = constrain_tools_for_task("Do not use the Python tool.", tools)
    assert requested is None
    assert [tool.name for tool in selected] == ["python_environment", "shell"]


def test_tool_diagnostic_arguments_are_bounded_and_redact_secrets():
    preview = _safe_tool_arguments({
        "query": "find a file",
        "api_key": "do-not-log-this",
        "nested": {"Authorization": "bearer-secret", "path": "report.txt"},
        "large": "x" * 5000,
    })
    assert "find a file" in preview
    assert "report.txt" in preview
    assert "do-not-log-this" not in preview
    assert "bearer-secret" not in preview
    assert "REDACTED" in preview
    assert len(preview) <= 1620
