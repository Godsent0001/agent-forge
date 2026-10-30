from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.tools import shell_capability


@pytest.mark.asyncio
async def test_typed_shell_runs_in_project_workspace_by_default(monkeypatch, tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    calls = []

    class FakeShell:
        async def execute(self, command, *, context):
            calls.append((command, context.workspace.root, context.timeout_seconds))
            return "Exit code: 0"

    monkeypatch.setattr(shell_capability, "LegacyShellTool", FakeShell)
    ctx = SimpleNamespace(
        execution_id="run-1", project_id="project-1", span_id="span-1",
        workspace=SimpleNamespace(root=project), cancel=None, config={},
    )
    tool = shell_capability.ShellCapability()
    result = await tool.run(tool.Input(command="python --version"), ctx)

    assert tool.Input.model_json_schema()["properties"].keys() == {"command", "working_directory", "timeout_seconds"}
    assert calls == [("python --version", project.resolve(), 60)]
    assert result.content == "Exit code: 0"
    assert not tool.requires_approval({"command": "python --version"})


@pytest.mark.asyncio
async def test_typed_shell_requires_approval_for_another_local_directory(monkeypatch, tmp_path: Path):
    project = tmp_path / "project"
    external = tmp_path / "documents"
    project.mkdir()
    external.mkdir()
    calls = []

    class FakeShell:
        async def execute(self, command, *, context):
            calls.append((command, context.workspace.root))
            return "Exit code: 0"

    monkeypatch.setattr(shell_capability, "LegacyShellTool", FakeShell)
    ctx = SimpleNamespace(
        execution_id="run-2", project_id="project-1", span_id="span-2",
        workspace=SimpleNamespace(root=project), cancel=None, config={},
    )
    tool = shell_capability.ShellCapability()
    assert tool.requires_approval({"working_directory": str(external)})
    result = await tool.run(
        tool.Input(command="dir", working_directory=str(external)), ctx
    )

    assert calls == [("dir", external.resolve(), 60)]
    assert result.ok


def test_default_factory_exposes_typed_shell_schema():
    from app.contracts.graph import ToolBinding
    from app.tools.registry import DefaultToolFactory

    tool = DefaultToolFactory().build(ToolBinding(id="shell-1", kind="shell", name="shell"))
    assert isinstance(tool, shell_capability.ShellCapability)
    assert {"command", "working_directory", "timeout_seconds"} == set(tool.Input.model_json_schema()["properties"])
