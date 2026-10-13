from __future__ import annotations

from pathlib import Path

from app.infra.paths import DATA_SUBDIRECTORIES, data_dir


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
