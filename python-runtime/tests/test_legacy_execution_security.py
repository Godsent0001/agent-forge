from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.contracts.graph import ToolBinding
from app.infra.workspace import RunWorkspace, data_dir
from app.tools.base import ToolExecutionError
from app.tools.registry import DefaultToolFactory


def _tool(kind: str):
    return DefaultToolFactory().build(ToolBinding(
        id=f"test-{kind}",
        kind=kind,
        name=kind,
        config={"root_dir": "/tmp/attacker-selected", "assets_dir": "/tmp/attacker-selected"},
    ))


def _context(tmp_path, execution_id="legacy-security-test"):
    workspace = RunWorkspace(
        execution_id,
        root=tmp_path / "runs" / execution_id,
        assets_root=tmp_path / "assets",
    )
    return SimpleNamespace(execution_id=execution_id, workspace=workspace)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["python", "http_request"])
async def test_legacy_engine_cannot_bypass_approval_for_high_risk_tools(kind, tmp_path):
    tool = _tool(kind)
    with pytest.raises(ToolExecutionError, match="legacy execution engine"):
        await tool.execute(
            "print('not run')" if kind == "python" else "GET https://example.com",
            context=_context(tmp_path),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(("kind", "payload"), [
    ("scene_template_manager", {"action": "save", "template_id": "safe", "template": {"x": 1}}),
    ("render_queue", {"action": "enqueue", "episode_id": "safe"}),
    ("render_queue", {"action": "update_status", "job_id": "safe", "status": "failed"}),
    ("project_manager", {"action": "scaffold", "episode_id": "safe"}),
    ("asset_cache_store", {"action": "put", "src_path": "input.wav", "category": "audio", "name": "safe"}),
    ("production_config", {"action": "set", "config": {"video": {"fps": 60}}}),
    ("cache_engine", {"action": "store", "inputs": {}, "output": {}}),
])
async def test_legacy_engine_denies_shared_state_mutations(kind, payload, tmp_path):
    tool = _tool(kind)
    with pytest.raises(ToolExecutionError, match="requires approval"):
        await tool.execute(json.dumps(payload), context=_context(tmp_path))


@pytest.mark.asyncio
async def test_legacy_engine_path_arguments_are_confined_to_per_run_workspace(tmp_path):
    tool = _tool("audio_processing")
    context = _context(tmp_path)
    assert tool.description
    with pytest.raises(ToolExecutionError, match="Parent-directory traversal|Unsafe workspace path"):
        await tool.execute(json.dumps({"audio_path": "../../escape.wav"}), context=context)
    assert not (tmp_path / "escape.wav").exists()


@pytest.mark.asyncio
async def test_legacy_file_system_can_write_inside_workspace_but_not_outside(tmp_path):
    tool = _tool("file_system")
    context = _context(tmp_path)
    await tool.execute("write:inside.txt::safe", context=context)
    assert (context.workspace.root / "files" / "inside.txt").read_text(encoding="utf-8") == "safe"
    with pytest.raises(ToolExecutionError):
        await tool.execute("write:../../outside.txt::blocked", context=context)
    assert not (tmp_path / "outside.txt").exists()


def test_legacy_tool_roots_ignore_user_supplied_storage_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTFORGE_DATA_DIR", str(tmp_path / "agentforge-data"))
    tool = _tool("visual_asset_manager")
    assert tool._legacy._root == (data_dir() / "assets" / "visuals").resolve()
    assert tool._legacy._root != Path("/tmp/attacker-selected")
