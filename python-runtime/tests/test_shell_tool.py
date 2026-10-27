from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.tools.shell import ShellTool


@pytest.mark.asyncio
async def test_shell_runs_command_and_saves_complete_output(tmp_path):
    context = SimpleNamespace(workspace=SimpleNamespace(root=tmp_path), span_id="shell-test")
    result = await ShellTool().execute('python -c "print(\'shell-ok\')"', context=context)

    assert "Exit code: 0" in result
    assert f"Project workspace: {tmp_path.resolve()}" in result
    assert "Full captured output:" in result
    assert "shell-ok" in result
    assert ".results/shell-shell-test.txt" in result
    saved = (tmp_path / ".results" / "shell-shell-test.txt").read_text(encoding="utf-8")
    assert "shell-ok" in saved


@pytest.mark.asyncio
async def test_shell_bounds_long_output_but_preserves_log(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.shell.MAX_OUTPUT_CHARS", 1000)
    monkeypatch.setattr("app.tools.shell.HEAD_CHARS", 300)
    monkeypatch.setattr("app.tools.shell.TAIL_CHARS", 300)
    context = SimpleNamespace(workspace=SimpleNamespace(root=tmp_path), span_id="large-log")
    result = await ShellTool().execute('python -c "print(\'x\' * 15000)"', context=context)

    assert len(result) < 2000
    assert "middle omitted" in result
    saved = (tmp_path / ".results" / "shell-large-log.txt").read_text(encoding="utf-8")
    assert len(saved) > 10_000


@pytest.mark.asyncio
async def test_shell_does_not_pass_provider_keys_to_child_process(tmp_path, monkeypatch):
    monkeypatch.setenv("VENICE_API_KEY", "must-not-leak")
    context = SimpleNamespace(workspace=SimpleNamespace(root=tmp_path), span_id="env-test")
    result = await ShellTool().execute(
        'python -c "import os; print(os.getenv(\'VENICE_API_KEY\'))"',
        context=context,
    )

    assert "must-not-leak" not in result
