from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.contracts.tools import ToolError
from app.tools.python_project import PythonProjectInput, PythonProjectTool


@pytest.mark.asyncio
async def test_shared_python_execute_dispatches_directly_to_python_executor():
    tool = PythonProjectTool()
    calls = []

    async def execute(code, *, context):
        calls.append((code, context))
        return "Exit code: 0\\npython-ok"

    tool._executor.execute = execute
    context = SimpleNamespace(workspace=SimpleNamespace(root="/tmp/project"))
    result = await tool.run(PythonProjectInput(code="print('python-ok')"), context)

    assert result.ok is True
    assert "python-ok" in result.content
    assert calls == [("print('python-ok')", context)]


@pytest.mark.parametrize("payload", [
    {"action": "ensure", "code": "print(1)"},
    {"action": "install", "packages": ["pandas>=2.0"]},
    {"action": "list", "code": ""},
])
def test_python_schema_does_not_expose_environment_or_venv_actions(payload):
    with pytest.raises(ValidationError):
        PythonProjectInput(**payload)


@pytest.mark.asyncio
async def test_shared_python_execute_requires_nonempty_code():
    tool = PythonProjectTool()
    with pytest.raises(ToolError, match="Provide Python source code"):
        await tool.run(
            PythonProjectInput(code="  "),
            SimpleNamespace(workspace=SimpleNamespace(root="/tmp/project")),
        )
