from __future__ import annotations

from pathlib import Path

from app import models
from app.infra import attachment_storage
from app.infra.attachment_storage import data_dir, upload_dirs
from app.routers import executions_v2


def _project(db_session, name: str = "Uploads"):
    project = models.Project(name=name)
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


def _upload(client, project_id: str, name: str = "brief.txt", content: bytes = b"Project brief"):
    return client.post(
        f"/v2/projects/{project_id}/attachments",
        files={"file": (name, content, "text/plain")},
    )


def test_upload_file_lists_and_downloads_without_scanning(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTFORGE_DATA_DIR", str(tmp_path / "data"))
    project = _project(db_session)

    response = _upload(client, project.id)
    assert response.status_code == 201, response.text
    attachment = response.json()
    assert attachment["status"] == "unscanned"
    assert attachment["name"] == "brief.txt"
    assert "storage_key" not in attachment
    assert "path" not in attachment

    listing = client.get(f"/v2/projects/{project.id}/attachments")
    assert listing.status_code == 200
    assert listing.json()["items"][0]["id"] == attachment["id"]

    download = client.get(f"/v2/projects/{project.id}/attachments/{attachment['id']}/content")
    assert download.status_code == 200
    assert download.content == b"Project brief"
    assert download.headers["content-disposition"].startswith("attachment")
    assert download.headers["x-content-type-options"] == "nosniff"
    assert download.headers["cache-control"] == "no-store"
    assert "sandbox" in download.headers["content-security-policy"]


def test_multiline_text_with_windows_newlines_and_tabs_is_accepted(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTFORGE_DATA_DIR", str(tmp_path / "data"))
    project = _project(db_session)

    content = b"Project brief\r\nOwner:\tKenny\r\n"
    response = _upload(client, project.id, "brief.txt", content)

    assert response.status_code == 201, response.text
    attachment = response.json()
    assert attachment["status"] == "clean"
    download = client.get(f"/v2/projects/{project.id}/attachments/{attachment['id']}/content")
    assert download.status_code == 200
    assert download.content == content

def test_uploads_are_available_without_invoking_scanner(client, db_session, tmp_path):
    monkeypatch.setenv("AGENTFORGE_DATA_DIR", str(tmp_path / "data"))
    project = _project(db_session)

    response = _upload(client, project.id)
    assert response.status_code == 201, response.text
    attachment = response.json()
    assert attachment["status"] == "unscanned"
    download = client.get(f"/v2/projects/{project.id}/attachments/{attachment['id']}/content")
    assert download.status_code == 200
    assert download.content == b"Project brief"

    agent = models.Agent(project_id=project.id, name="Upload agent")
    db_session.add(agent)
    db_session.commit()
    captured = {}
    def capture(req):
        captured["req"] = req
        return {"id": req.execution_id, "status": "running"}

    monkeypatch.setattr(executions_v2.manager, "start", capture)
    start = client.post("/v2/executions", json={
        "project_id": project.id,
        "root_agent_id": agent.id,
        "task": "Read the attached brief",
        "attachment_ids": [attachment["id"]],
    })
    assert start.status_code == 200, start.text
    assert captured["req"].attachments[0].scan_status == "unscanned"
    run_file = data_dir() / "runs" / captured["req"].execution_id / captured["req"].attachments[0].path
    assert run_file.read_bytes() == b"Project brief"



def test_python_source_attachment_is_validated_and_available_for_inspection(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTFORGE_DATA_DIR", str(tmp_path / "data"))
    project = _project(db_session)
    source = b"def add(a, b):\n    return a + b\n"
    response = _upload(client, project.id, "calculator.py", source)
    assert response.status_code == 201, response.text
    attachment = response.json()
    assert attachment["status"] == "unscanned"
    assert attachment["mime"] == "text/x-python"
    download = client.get(f"/v2/projects/{project.id}/attachments/{attachment['id']}/content")
    assert download.status_code == 200
    assert download.content == source


def test_upload_does_not_run_antivirus_or_quarantine(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTFORGE_DATA_DIR", str(tmp_path / "data"))
    project = _project(db_session)

    response = _upload(client, project.id, "sample.bin", b"\x00\x01arbitrary binary")
    assert response.status_code == 201, response.text
    attachment = response.json()
    assert attachment["status"] == "unscanned"
    download = client.get(f"/v2/projects/{project.id}/attachments/{attachment['id']}/content")
    assert download.status_code == 200
    assert download.content == b"\x00\x01arbitrary binary"


def test_upload_accepts_active_or_mismatched_content_as_untrusted_input(client, db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTFORGE_DATA_DIR", str(tmp_path / "data"))
    project = _project(db_session)
    html = _upload(client, project.id, "readme.txt", b"<html><script>alert(1)</script></html>")
    mismatch = _upload(client, project.id, "portrait.png", b"plain text")
    assert html.status_code == 201, html.text
    assert mismatch.status_code == 201, mismatch.text
    assert html.json()["status"] == "unscanned"
    assert mismatch.json()["status"] == "unscanned"


def test_attachment_ids_are_project_scoped_and_run_gets_private_copy(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTFORGE_DATA_DIR", str(tmp_path / "data"))
    project = _project(db_session)
    other = _project(db_session, "Other")
    response = _upload(client, project.id)
    attachment = response.json()

    hidden = client.get(f"/v2/projects/{other.id}/attachments/{attachment['id']}")
    assert hidden.status_code == 404

    agent = models.Agent(project_id=project.id, name="Upload agent")
    db_session.add(agent)
    db_session.commit()
    captured = {}

    def capture(req):
        captured["req"] = req
        return {"id": req.execution_id, "status": "running"}

    monkeypatch.setattr(executions_v2.manager, "start", capture)
    start = client.post(
        "/v2/executions",
        json={
            "project_id": project.id,
            "root_agent_id": agent.id,
            "task": "Summarize the attached brief",
            "attachment_ids": [attachment["id"]],
        },
    )
    assert start.status_code == 200, start.text
    req = captured["req"]
    assert len(req.attachments) == 1
    assert req.attachments[0].path.startswith("attachments/")
    run_file = data_dir() / "runs" / req.execution_id / req.attachments[0].path
    assert run_file.read_bytes() == b"Project brief"


def test_delete_removes_metadata_and_blobs(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTFORGE_DATA_DIR", str(tmp_path / "data"))
    project = _project(db_session)
    response = _upload(client, project.id)
    attachment = response.json()
    row = db_session.get(models.ProjectAttachment, attachment["id"])
    assert row is not None
    key = row.storage_key
    root, _, objects = upload_dirs()
    stored = objects / f"{key}.blob"
    assert stored.exists()

    deleted = client.delete(f"/v2/projects/{project.id}/attachments/{attachment['id']}")
    assert deleted.status_code == 200
    assert not stored.exists()
    assert client.get(f"/v2/projects/{project.id}/attachments/{attachment['id']}").status_code == 404


def test_windows_defender_scanner_is_found_in_platform_or_default_directory(monkeypatch, tmp_path):
    platform_dir = tmp_path / "Microsoft" / "Windows Defender" / "Platform" / "4.18.1"
    platform_dir.mkdir(parents=True)
    scanner = platform_dir / "MpCmdRun.exe"
    scanner.write_bytes(b"test executable")
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path))
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "Program Files"))

    assert attachment_storage._find_windows_defender_scanner() == str(scanner)


async def test_windows_defender_only_returns_clean_for_successful_non_remediating_scan(monkeypatch, tmp_path):
    class FakeProcess:
        def __init__(self, returncode):
            self.returncode = returncode

        async def communicate(self):
            return b"", b""

    async def run_clean(*args, **kwargs):
        return FakeProcess(0)

    async def run_uncertain(*args, **kwargs):
        return FakeProcess(2)

    monkeypatch.setattr(attachment_storage.asyncio, "create_subprocess_exec", run_clean)
    assert await attachment_storage._scan_with_windows_defender(tmp_path / "brief.txt", "MpCmdRun.exe") == (
        "clean",
        "Microsoft Defender Antivirus",
    )

    monkeypatch.setattr(attachment_storage.asyncio, "create_subprocess_exec", run_uncertain)
    assert await attachment_storage._scan_with_windows_defender(tmp_path / "brief.txt", "MpCmdRun.exe") == (
        "error",
        "Microsoft Defender Antivirus",
    )
