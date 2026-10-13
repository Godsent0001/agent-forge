from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.contracts.tools import ToolError
from app.infra.workspace import RunWorkspace
from app.tools.adapter import _normalize_payload


@pytest.fixture()
def context(tmp_path):
    workspace = RunWorkspace(
        "adapter-test",
        root=tmp_path / "run",
        assets_root=tmp_path / "assets",
    )
    return SimpleNamespace(workspace=workspace)


def test_audio_input_and_default_output_are_scoped_to_run_workspace(context):
    payload = json.loads(_normalize_payload(
        "audio_processing",
        json.dumps({"audio_path": "./output/source.wav"}),
        context,
    ))
    root = context.workspace.root
    assert payload["audio_path"] == str(root / "source.wav")
    assert payload["output_path"] == str(root / "processed_voice.wav")
    assert (root / "processed_voice.wav").parent.is_dir()


@pytest.mark.parametrize("value", [
    "../outside.wav",
    "nested/../../outside.wav",
    "/etc/passwd",
    r"C:\\Windows\\system.ini",
    r"\\\\server\\share\\secret.txt",
])
def test_path_arguments_reject_traversal_and_absolute_paths(context, value):
    with pytest.raises(ToolError):
        _normalize_payload("audio_processing", json.dumps({"audio_path": value}), context)


def test_nested_composition_paths_are_resolved_inside_workspace(context):
    payload = json.loads(_normalize_payload(
        "composition_engine",
        json.dumps({
            "layers": [{"image_path": "assets/frame.png", "x": 0, "y": 0}],
            "output_path": "./output/final.png",
        }),
        context,
    ))
    root = context.workspace.root
    assert payload["layers"][0]["image_path"] == str(root / "assets" / "frame.png")
    assert payload["output_path"] == str(root / "final.png")


def test_symlink_escape_is_blocked_for_tool_input(context, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (context.workspace.root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ToolError):
        _normalize_payload(
            "audio_processing",
            json.dumps({"audio_path": "link/secret.wav"}),
            context,
        )


def test_project_and_asset_identifiers_are_validated(context):
    with pytest.raises(ToolError):
        _normalize_payload("project_manager", json.dumps({"episode_id": "../escape"}), context)
    with pytest.raises(ToolError):
        _normalize_payload("asset_cache_store", json.dumps({
            "action": "store", "src_path": "input.wav", "category": "../outside", "name": "x"
        }), context)
    with pytest.raises(ToolError):
        _normalize_payload("visual_asset_manager", json.dumps({"action": "get", "name": "../secret"}), context)
