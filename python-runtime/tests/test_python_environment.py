from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.contracts.tools import ToolError
from app.tools import python_environment
from app.tools.python_environment import PythonEnvironmentInput, PythonEnvironmentTool


def context(root):
    root.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(workspace=SimpleNamespace(root=root))


@pytest.mark.asyncio
async def test_environment_ensure_creates_persistent_project_venv(tmp_path, monkeypatch):
    tool = PythonEnvironmentTool()
    ctx = context(tmp_path)

    async def fake_run(command, *, cwd):
        venv_python = tmp_path / (".venv/Scripts/python.exe" if __import__("os").name == "nt" else ".venv/bin/python")
        venv_python.parent.mkdir(parents=True, exist_ok=True)
        venv_python.write_text("", encoding="utf-8")
        return 0, "created"

    monkeypatch.setattr("app.tools.python_environment._run", fake_run)
    monkeypatch.setattr("app.tools.python_environment._base_python", lambda: ["python"])
    result = await tool.run(PythonEnvironmentInput(action="ensure"), ctx)
    assert '"status": "ready"' in result.content
    assert (tmp_path / ".venv").is_dir()


@pytest.mark.asyncio
async def test_environment_install_records_requirements_in_workspace(tmp_path, monkeypatch):
    tool = PythonEnvironmentTool()
    ctx = context(tmp_path)
    venv_python = tmp_path / (".venv/Scripts/python.exe" if __import__("os").name == "nt" else ".venv/bin/python")
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("", encoding="utf-8")

    async def fake_run(command, *, cwd):
        assert str(venv_python) in command[0]
        assert "install" in command
        return 0, "Successfully installed demo-package"

    monkeypatch.setattr("app.tools.python_environment._run", fake_run)
    result = await tool.run(PythonEnvironmentInput(action="install", packages=["demo-package>=1.2"]), ctx)
    assert result.content.find("installed") >= 0
    assert (tmp_path / "requirements.txt").read_text(encoding="utf-8") == "demo-package>=1.2\n"


@pytest.mark.asyncio
async def test_environment_rejects_pip_flags_and_urls(tmp_path, monkeypatch):
    tool = PythonEnvironmentTool()
    ctx = context(tmp_path)
    with pytest.raises(ToolError, match="Invalid package specifier"):
        await tool.run(PythonEnvironmentInput(action="install", packages=["--index-url=https://bad.example"]), ctx)


def test_environment_tool_requires_network_and_subprocess_permissions():
    assert PythonEnvironmentTool.permissions == {"net", "subprocess"}


def test_packaged_environment_prefers_bundled_python(tmp_path, monkeypatch):
    home = tmp_path / "python-interpreter"
    import os

    executable = home / ("python.exe" if os.name == "nt" else "bin/python3.11")
    executable.parent.mkdir(parents=True)
    executable.write_text("", encoding="utf-8")
    monkeypatch.setattr(python_environment.sys, "frozen", True, raising=False)
    monkeypatch.setenv("AGENTFORGE_PYTHON_HOME", str(home))
    monkeypatch.setattr(python_environment.shutil, "which", lambda _: None)

    assert python_environment._base_python() == [str(executable)]
