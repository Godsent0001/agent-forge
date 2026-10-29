from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.contracts.tools import ToolResult
from app.tools.python_project import PythonProjectInput, PythonProjectTool


@pytest.mark.asyncio
async def test_unified_python_tool_dispatches_execution(monkeypatch, tmp_path):
    tool = PythonProjectTool()
    context = SimpleNamespace(workspace=SimpleNamespace(root=tmp_path), span_id="python-test")
    calls = {}

    async def execute(code, *, context):
        calls["code"] = code
        calls["context"] = context
        return "python-result"

    monkeypatch.setattr(tool._executor, "execute", execute)
    async def ensure(args, ctx):
        calls["ensure_action"] = args.action
        return ToolResult(content="environment-ready")
    monkeypatch.setattr(tool._environment, "run", ensure)
    result = await tool.run(PythonProjectInput(action="execute", code="print(1 + 1)"), context)

    assert calls["ensure_action"] == "ensure"
    assert result.ok
    assert result.content == "python-result"
    assert calls["code"] == "print(1 + 1)"
    assert calls["context"] is context


@pytest.mark.asyncio
async def test_unified_python_tool_dispatches_environment_actions(monkeypatch, tmp_path):
    tool = PythonProjectTool()
    context = SimpleNamespace(workspace=SimpleNamespace(root=tmp_path), span_id="python-env-test")
    calls = {}

    async def manage(args, ctx):
        calls["action"] = args.action
        calls["packages"] = args.packages
        calls["context"] = ctx
        return ToolResult(content="environment-ready")

    monkeypatch.setattr(tool._environment, "run", manage)
    result = await tool.run(
        PythonProjectInput(action="install", packages=["pandas>=2.0"]),
        context,
    )

    assert result.content == "environment-ready"
    assert calls == {
        "action": "install",
        "packages": ["pandas>=2.0"],
        "context": context,
    }


def test_unified_python_tool_requires_approval_for_environment_mutations():
    tool = PythonProjectTool()
    assert not tool.requires_approval({"action": "execute"})
    assert not tool.requires_approval({"action": "ensure"})
    assert tool.requires_approval({"action": "install"})
    assert tool.permissions_for({"action": "install"}) == {"subprocess", "net"}
    assert tool.permissions_for({"action": "execute"}) == {"subprocess"}


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
    assert {"action", "code", "packages"} <= set(python_specs[0].parameters["properties"])
    assert "file" in instances
    assert "knowledge_search" in instances
    assert "knowledge_ingest" in instances
