from __future__ import annotations

from app.infra.paths import project_dir
from app.services.core_adapters import Workspace


def test_project_workspace_persists_across_executions(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTFORGE_DATA_DIR", str(tmp_path / "agentforge-data"))
    first = Workspace("run-one", "project_123")
    file = first.resolve("calculator/main.py")
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("print('calculator')", encoding="utf-8")
    first.cleanup()

    second = Workspace("run-two", "project_123")
    assert second.root == first.root
    assert second.resolve("calculator/main.py").read_text(encoding="utf-8") == "print('calculator')"
    assert second.root == (project_dir("project_123") / "workspace").resolve()


def test_project_workspace_is_separate_between_projects(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTFORGE_DATA_DIR", str(tmp_path / "agentforge-data"))
    first = Workspace("run-one", "project-one")
    second = Workspace("run-two", "project-two")
    assert first.root != second.root
