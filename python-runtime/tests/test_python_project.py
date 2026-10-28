from types import SimpleNamespace

import pytest

from app.contracts.tools import ToolError
from app.tools.python_project import PythonProjectInput, PythonProjectTool


@pytest.mark.asyncio
async def test_unified_python_execute_dispatches_to_python_executor():
    tool = PythonProjectTool()
    calls = []

    async def execute(code, *, context):
        calls.append((code, context))
        return "Exit code: 0\npython-ok"

    tool._executor.execute = execute
    context = SimpleNamespace(workspace=SimpleNamespace(root="/tmp/project"))
    result = await tool.run(PythonProjectInput(action="execute", code="print('python-ok')"), context)

    assert result.ok is True
    assert "python-ok" in result.content
    assert calls == [("print('python-ok')", context)]


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["ensure", "install", "list"])
async def test_unified_python_environment_actions_dispatch_to_environment_tool(action):
    tool = PythonProjectTool()
    calls = []

    async def run(args, context):
        calls.append((args.action, args.packages, context))
        from app.contracts.tools import ToolResult

        return ToolResult(content=f"environment:{args.action}")

    tool._environment.run = run
    context = SimpleNamespace(workspace=SimpleNamespace(root="/tmp/project"))
    packages = ["pandas>=2.0"] if action == "install" else []
    result = await tool.run(PythonProjectInput(action=action, packages=packages), context)

    assert result.content == f"environment:{action}"
    assert calls == [(action, packages, context)]


@pytest.mark.asyncio
async def test_unified_python_execute_requires_nonempty_code():
    tool = PythonProjectTool()
    with pytest.raises(ToolError, match="Provide Python source code"):
        await tool.run(
            PythonProjectInput(action="execute", code="  "),
            SimpleNamespace(workspace=SimpleNamespace(root="/tmp/project")),
        )
