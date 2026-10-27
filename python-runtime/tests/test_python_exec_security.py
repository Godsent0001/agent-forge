from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.tools.base import ToolExecutionError
from app.tools.python_exec import PythonExecTool


@pytest.mark.asyncio
async def test_python_tool_strips_markdown_fences():
    tool = PythonExecTool()
    result = await tool.execute("```python\nprint('fence-ok')\n```", context=SimpleNamespace())
    assert result == "fence-ok\n"


@pytest.mark.asyncio
async def test_python_tool_caps_stdout(monkeypatch):
    tool = PythonExecTool()
    result = await tool.execute("print('x' * 15000)", context=SimpleNamespace())
    assert len(result) <= 10_012
    assert result.endswith("…[truncated]")


@pytest.mark.asyncio
async def test_python_tool_does_not_inherit_api_keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "do-not-leak")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "do-not-leak-either")
    tool = PythonExecTool()
    result = await tool.execute(
        "import os; print(' '.join(sorted(os.environ.keys())))",
        context=SimpleNamespace(),
    )
    assert "OPENAI_API_KEY" not in result
    assert "ANTHROPIC_API_KEY" not in result


@pytest.mark.asyncio
async def test_python_tool_enforces_wall_clock_timeout(monkeypatch):
    monkeypatch.setattr("app.tools.python_exec.WALL_CLOCK_TIMEOUT_SECONDS", 0.75)
    tool = PythonExecTool()
    with pytest.raises(ToolExecutionError, match="wall-clock limit"):
        await tool.execute("import time; time.sleep(5)", context=SimpleNamespace())


@pytest.mark.asyncio
async def test_python_snippet_can_import_project_files_from_persistent_workspace(tmp_path):
    module = tmp_path / "project_module.py"
    module.write_text("VALUE = 'workspace-import-ok'\\n", encoding="utf-8")
    ctx = SimpleNamespace(workspace=SimpleNamespace(root=tmp_path))
    result = await PythonExecTool().execute(
        "import project_module; print(project_module.VALUE)",
        context=ctx,
    )
    assert result.strip() == "workspace-import-ok"
