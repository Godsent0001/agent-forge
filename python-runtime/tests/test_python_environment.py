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


def test_packaged_environment_uses_compatible_system_python(monkeypatch):
    monkeypatch.setattr(python_environment.sys, "frozen", True, raising=False)
    monkeypatch.setattr(python_environment.os, "name", "posix")
    monkeypatch.setattr(python_environment.shutil, "which", lambda command: "/usr/bin/python3" if command == "python3" else None)
    monkeypatch.setattr(
        python_environment.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="Python 3.12.4", stderr=""),
    )

    assert python_environment._base_python() == ["/usr/bin/python3"]


def test_packaged_environment_explains_missing_python(monkeypatch):
    monkeypatch.setattr(python_environment.sys, "frozen", True, raising=False)
    monkeypatch.setattr(python_environment.shutil, "which", lambda _: None)

    with pytest.raises(ToolError, match="Install Python 3.11"):
        python_environment._base_python()


def test_packaged_environment_falls_back_when_launcher_is_incompatible(monkeypatch):
    monkeypatch.setattr(python_environment.sys, "frozen", True, raising=False)
    monkeypatch.setattr(python_environment.os, "name", "nt")
    monkeypatch.setattr(
        python_environment.shutil,
        "which",
        lambda command: {
            "py": r"C:\\Windows\\py.exe",
            "python3": r"C:\\Python312\\python.exe",
            "python": None,
        }.get(command),
    )

    def fake_run(command, **kwargs):
        if command[0].endswith("py.exe"):
            return SimpleNamespace(returncode=1, stdout="", stderr="No suitable Python runtime found")
        return SimpleNamespace(returncode=0, stdout="Python 3.12.4", stderr="")

    monkeypatch.setattr(python_environment.subprocess, "run", fake_run)
    assert python_environment._base_python() == [r"C:\\Python312\\python.exe"]
