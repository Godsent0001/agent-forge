from __future__ import annotations

import io
import zipfile

from app.infra.paths import project_dir


def test_project_workspace_can_be_listed_and_downloaded(client, monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTFORGE_DATA_DIR", str(tmp_path / "agentforge-data"))
    project_response = client.post("/projects", json={"name": "Calculator"})
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    workspace = project_dir(project_id) / "workspace"
    app_dir = workspace / "calculator"
    app_dir.mkdir(parents=True)
    (app_dir / "main.py").write_text("print(2 + 2)", encoding="utf-8")
    (workspace / ".results").mkdir()
    (workspace / ".results" / "shell-log.txt").write_text("internal log", encoding="utf-8")

    listed = client.get(f"/projects/{project_id}/workspace")
    assert listed.status_code == 200
    body = listed.json()
    assert body["file_count"] == 1
    assert body["files"][0]["path"] == "calculator/main.py"
    assert body["workspace_path"] == str(workspace.resolve())

    downloaded = client.get(f"/projects/{project_id}/workspace.zip")
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(io.BytesIO(downloaded.content)) as archive:
        assert archive.namelist() == ["calculator/main.py"]
        assert archive.read("calculator/main.py").decode("utf-8") == "print(2 + 2)"


def test_project_tool_delete_removes_only_project_instance(client):
    project_id = client.post("/projects", json={"name": "Tools"}).json()["id"]
    agent_id = client.post("/agents", json={"project_id": project_id, "name": "Agent"}).json()["id"]
    tool_response = client.post("/tools", json={"project_id": project_id, "name": "web search", "kind": "web_search"})
    assert tool_response.status_code == 200
    tool_id = tool_response.json()["id"]
    assert client.post("/agents/attach-tool", json={"agent_id": agent_id, "tool_id": tool_id}).status_code == 200

    removed = client.delete(f"/tools/{tool_id}")
    assert removed.status_code == 200
    assert removed.json() == {"deleted": tool_id, "scope": "project"}
    assert client.get(f"/tools?project_id={project_id}").json() == []
    assert client.get(f"/agents/{agent_id}").json()["tool_ids"] == []
    # Global definitions are independent from project tool instances.
    from app.tools.catalog import CATALOG
    assert any(item.kind == "web_search" for item in CATALOG)
