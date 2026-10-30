from __future__ import annotations

import json

from app.services import previews
from app.services.core_adapters import Workspace


class FakeProcess:
    pid = 12345

    def __init__(self):
        self.returncode = None

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = 0
        return 0

    def kill(self):
        self.returncode = -9


def test_preview_manager_starts_and_reports_a_vite_app(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTFORGE_DATA_DIR", str(tmp_path / "agentforge-data"))
    monkeypatch.setenv("TEST_PROVIDER_API_KEY", "must-not-leak")
    workspace = Workspace("preview-manager-test", "project-preview-test")
    app_dir = workspace.root / "app"
    app_dir.mkdir()
    package_file = app_dir / "package.json"
    package_file.write_text(json.dumps({"scripts": {"dev": "vite"}}), encoding="utf-8")

    captured = {}
    process = FakeProcess()

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return process

    monkeypatch.setattr(previews.shutil, "which", lambda _name: "/usr/bin/npm")
    monkeypatch.setattr(previews.PreviewManager, "_port", staticmethod(lambda: 45678))
    monkeypatch.setattr(previews.subprocess, "Popen", fake_popen)
    manager = previews.PreviewManager()
    monkeypatch.setattr(manager, "_is_listening", lambda _port: True)
    monkeypatch.setattr(manager, "_terminate", lambda _item: None)

    started = manager.start("preview-manager-test", "app/package.json", project_id="project-preview-test")
    assert started["status"] == "starting"
    assert captured["cwd"] == str(app_dir)
    assert "--host" in captured["command"]
    assert "127.0.0.1" in captured["command"]
    assert "45678" in captured["command"]
    assert "TEST_PROVIDER_API_KEY" not in captured["env"]

    ready = manager.status("preview-manager-test")
    assert ready["status"] == "ready"
    assert ready["url"] == "http://127.0.0.1:45678"
    assert manager.stop("preview-manager-test")["status"] == "stopped"


def test_preview_manager_rejects_package_without_dev_or_start_script(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTFORGE_DATA_DIR", str(tmp_path / "agentforge-data"))
    workspace = Workspace("preview-invalid-test", "project-preview-invalid-test")
    (workspace.root / "package.json").write_text(json.dumps({"scripts": {"test": "vitest"}}), encoding="utf-8")
    manager = previews.PreviewManager()
    monkeypatch.setattr(previews.shutil, "which", lambda _name: "/usr/bin/npm")

    try:
        manager.start("preview-invalid-test", "package.json", project_id="project-preview-invalid-test")
    except ValueError as exc:
        assert "dev" in str(exc) and "start" in str(exc)
    else:
        raise AssertionError("Expected a package script validation error")
