from __future__ import annotations

from types import SimpleNamespace

import os

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
    module.write_text("VALUE = 'workspace-import-ok'\n", encoding="utf-8")
    ctx = SimpleNamespace(workspace=SimpleNamespace(root=tmp_path))
    result = await PythonExecTool().execute(
        "import project_module; print(project_module.VALUE)",
        context=ctx,
    )
    assert result.strip() == "workspace-import-ok"


def test_python_execution_has_startup_headroom_for_desktop_runtime():
    from app.tools import python_exec

    assert python_exec.WALL_CLOCK_TIMEOUT_SECONDS >= 60
    assert python_exec.CPU_TIME_LIMIT_SECONDS >= 30
    assert python_exec.MEMORY_LIMIT_BYTES >= 1024 * 1024 * 1024


@pytest.mark.asyncio
async def test_python_tool_uses_explicit_shared_interpreter(monkeypatch):
    import sys

    monkeypatch.setenv("AGENTFORGE_PYTHON_EXECUTABLE", sys.executable)
    tool = PythonExecTool()
    result = await tool.execute("print(2 + 2)", context=SimpleNamespace())
    assert result.strip() == "4"


def test_python_interpreter_discovery_skips_virtual_environment_path(monkeypatch, tmp_path):
    from app.tools import python_exec

    system_bin = tmp_path / "Python311"
    system_bin.mkdir()
    system_python = system_bin / ("python.exe" if python_exec.os.name == "nt" else "python3")
    system_python.write_text("", encoding="utf-8")
    venv_bin = tmp_path / ".venv" / "Scripts"
    venv_bin.mkdir(parents=True)
    monkeypatch.delenv("AGENTFORGE_PYTHON_EXECUTABLE", raising=False)
    monkeypatch.setenv("PATH", str(venv_bin) + os.pathsep + str(system_bin))
    monkeypatch.setattr(python_exec.shutil, "which", lambda name, path=None: str(system_python) if "Python311" in (path or "") else None)
    assert python_exec._resolve_shared_python_command() == [str(system_python)]
