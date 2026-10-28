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
    result = await tool.run(PythonProjectInput(action="execute", code="print(1 + 1)"), context)

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
    assert tool.requires_approval({"action": "ensure"})
    assert tool.requires_approval({"action": "install"})
    assert tool.permissions_for({"action": "install"}) == {"subprocess", "net"}
    assert tool.permissions_for({"action": "execute"}) == {"subprocess"}
