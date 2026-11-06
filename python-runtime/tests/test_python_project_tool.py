from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.tools.python_project import PythonProjectInput, PythonProjectTool


@pytest.mark.asyncio
async def test_python_tool_executes_directly_without_environment_setup(monkeypatch, tmp_path):
    tool = PythonProjectTool()
    context = SimpleNamespace(workspace=SimpleNamespace(root=tmp_path), span_id="python-test")
    calls = {}

    async def execute(code, *, context):
        calls["code"] = code
        calls["context"] = context
        return "python-result"

    monkeypatch.setattr(tool._executor, "execute", execute)
    result = await tool.run(PythonProjectInput(code="print(1 + 1)"), context)

    assert result.ok
    assert result.content == "python-result"
    assert calls["code"] == "print(1 + 1)"
    assert calls["context"] is context
    assert not hasattr(tool, "_environment")


def test_python_tool_schema_has_no_venv_or_environment_actions():
    schema = PythonProjectInput.model_json_schema()
    assert set(schema["properties"]) == {"code"}
    with pytest.raises(ValidationError):
        PythonProjectInput(action="ensure", code="print(1)")
    with pytest.raises(ValidationError):
        PythonProjectInput(action="install", packages=["pandas"])


def test_runner_collapses_legacy_python_bindings_into_one_model_tool():
    from app.contracts.graph import AgentGraph, AgentSpec, ToolBinding
    from app.core.runner import RunnerCore
    from app.tools.python_project import PythonProjectTool
    from app.tools.registry import DefaultToolFactory

    spec = AgentSpec(
        id="agent-1", name="Test agent", provider="venice", model="test-model",
        tools=[
            ToolBinding(id="python-id", kind="python", name="Python Execution"),
            ToolBinding(id="python-env-id", kind="python_environment", name="Python Environment"),
        ],
    )
    graph = AgentGraph(root_id=spec.id, agents={spec.id: spec})
    tool_specs, instances = RunnerCore()._assemble_tools(
        spec, graph, DefaultToolFactory(), memory=None, intents=None, run_history=None
    )

    python_specs = [tool for tool in tool_specs if tool.name == "python"]
    assert len(python_specs) == 1
    assert isinstance(instances["python"], PythonProjectTool)
    assert set(python_specs[0].parameters["properties"]) == {"code"}
    assert "file" in instances
    assert "knowledge_search" in instances
    assert "knowledge_ingest" in instances


@pytest.mark.asyncio
async def test_python_tool_reports_executor_errors(monkeypatch, tmp_path):
    from app.contracts.tools import ToolError
    from app.tools.base import ToolExecutionError

    tool = PythonProjectTool()
    context = SimpleNamespace(workspace=SimpleNamespace(root=tmp_path), span_id="python-error-test")

    async def execute(code, *, context):
        raise ToolExecutionError("python runtime unavailable")

    monkeypatch.setattr(tool._executor, "execute", execute)
    with pytest.raises(ToolError, match="python runtime unavailable"):
        await tool.run(PythonProjectInput(code="print(2 + 2)"), context)
