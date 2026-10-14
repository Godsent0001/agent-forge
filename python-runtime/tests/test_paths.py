from __future__ import annotations

from app.infra.paths import DATA_SUBDIRECTORIES, data_dir
from app.tools.asset_cache import (
    AssetCacheStoreTool,
    CacheEngineTool,
    ProductionConfigTool,
    ProjectManagerTool,
)
from app.tools.audio import VoiceGeneratorTool
from app.tools.character import CharacterAssetManagerTool
from app.tools.graphics import VisualAssetManagerTool
from app.tools.rendering import RenderQueueTool
from app.tools.scene import SceneTemplateManagerTool


def test_data_dir_uses_configured_root_and_creates_standard_directories(monkeypatch, tmp_path):
    configured = tmp_path / "agentforge-user-data"
    monkeypatch.setenv("AGENTFORGE_DATA_DIR", str(configured))

    root = data_dir()

    assert root == configured.resolve()
    assert all((root / name).is_dir() for name in DATA_SUBDIRECTORIES)
    assert {"db", "runs", "assets", "queues", "logs"}.issubset(DATA_SUBDIRECTORIES)


def test_database_path_default_is_under_user_data():
    # This verifies path construction without depending on the host's working directory.
    import app.db as db

    assert db.DB_PATH.name == "agentforge.db"
    assert db.DB_PATH.parent.name == "db"
    assert db.DB_PATH.is_absolute()


def test_workspace_legacy_fallback_is_under_data_directory(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from app.infra.workspace import workspace_from

    root = tmp_path / "agentforge-user-data"
    monkeypatch.setenv("AGENTFORGE_DATA_DIR", str(root))
    workspace = workspace_from(SimpleNamespace())
    assert workspace.root == (root / "output").resolve()


def test_legacy_tool_storage_defaults_follow_configured_data_directory(monkeypatch, tmp_path):
    root = tmp_path / "agentforge-user-data"
    monkeypatch.setenv("AGENTFORGE_DATA_DIR", str(root))

    assert CacheEngineTool()._root == root / "cache"
    assert ProjectManagerTool()._root == root / "projects"
    assert AssetCacheStoreTool()._root == root / "assets" / "shared"
    assert ProductionConfigTool()._path == root / "production_config.json"
    assert VoiceGeneratorTool()._voices_dir == root / "assets" / "voices"
    assert CharacterAssetManagerTool()._root == root / "assets" / "characters"
    assert VisualAssetManagerTool()._root == root / "assets" / "visuals"
    assert RenderQueueTool()._path == root / "queues" / "render_queue.json"
    assert SceneTemplateManagerTool()._root == root / "assets" / "scene_templates"
