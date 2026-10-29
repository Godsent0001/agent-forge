from __future__ import annotations

from app import models
from app.contracts.artifacts import ArtifactCreate
from app.core.artifact_store import SQLiteArtifactStore
from app.infra.paths import project_dir
from app.routers import executions_v2


def test_execution_artifacts_are_project_scoped_and_downloadable(
    client, db_session, monkeypatch, tmp_path
):
    monkeypatch.setenv("AGENTFORGE_DATA_DIR", str(tmp_path / "agentforge-data"))
    monkeypatch.setattr(executions_v2, "SessionLocal", lambda: db_session)

    project = models.Project(name="artifact API project")
    agent = models.Agent(project=project, name="artifact API agent")
    db_session.add_all([project, agent])
    db_session.commit()

    execution = models.Execution(
        id="artifact-api-run",
        project_id=project.id,
        root_agent_id=agent.id,
        input_task="Generate an artifact",
        status="completed",
    )
    db_session.add(execution)
    db_session.commit()

    store = SQLiteArtifactStore(project_dir(project.id))
    record = store.create(
        ArtifactCreate(
            project_id=project.id,
            artifact_type="execution_output",
            name="answer.txt",
            media_type="text/plain",
            metadata={"execution_id": execution.id},
        ),
        b"persisted answer",
    )
    other_execution = models.Execution(
        id="another-artifact-api-run",
        project_id=project.id,
        root_agent_id=agent.id,
        input_task="Another execution",
        status="completed",
    )
    db_session.add(other_execution)
    db_session.commit()
    other_run_record = store.create(
        ArtifactCreate(
            project_id=project.id,
            artifact_type="execution_output",
            name="other-run.txt",
            metadata={"execution_id": other_execution.id},
        ),
        b"other run output",
    )

    foreign = store.create(
        ArtifactCreate(
            project_id="another-project",
            artifact_type="execution_output",
            name="foreign.txt",
            metadata={"execution_id": execution.id},
        ),
        b"must not be exposed",
    )

    listed = client.get(f"/v2/executions/{execution.id}/artifacts")
    assert listed.status_code == 200
    assert [item["artifact_id"] for item in listed.json()] == [record.artifact_id]

    downloaded = client.get(
        f"/v2/executions/{execution.id}/artifacts/{record.artifact_id}?version=1"
    )
    assert downloaded.status_code == 200
    assert downloaded.content == b"persisted answer"
    assert downloaded.headers["content-disposition"].startswith("inline;")
    assert downloaded.headers["x-content-type-options"] == "nosniff"

    denied = client.get(f"/v2/executions/{execution.id}/artifacts/{foreign.artifact_id}")
    assert denied.status_code == 404
    cross_run = client.get(f"/v2/executions/{execution.id}/artifacts/{other_run_record.artifact_id}")
    assert cross_run.status_code == 404


def test_large_artifacts_stream_from_disk_and_support_range_requests(
    client, db_session, monkeypatch, tmp_path
):
    monkeypatch.setenv("AGENTFORGE_DATA_DIR", str(tmp_path / "agentforge-data"))
    monkeypatch.setattr(executions_v2, "SessionLocal", lambda: db_session)
    project = models.Project(name="streaming")
    agent = models.Agent(project=project, name="agent")
    db_session.add_all([project, agent])
    db_session.commit()
    execution = models.Execution(id="stream-run", project_id=project.id, root_agent_id=agent.id,
                                 input_task="t", status="completed")
    db_session.add(execution)
    db_session.commit()

    source = tmp_path / "clip.mp4"
    content = bytes(range(256)) * 12_000  # ~3 MB, spans several read chunks
    source.write_bytes(content)
    store = SQLiteArtifactStore(project_dir(project.id))
    spec = ArtifactCreate(project_id=project.id, artifact_type="tool_artifact", name="clip.mp4",
                          media_type="video/mp4", metadata={"execution_id": execution.id})
    streamed = store.create_from_file(spec, source)
    in_memory = store.create(spec, content)
    assert streamed.sha256 == in_memory.sha256 and streamed.size_bytes == len(content)

    url = f"/v2/executions/{execution.id}/artifacts/{streamed.artifact_id}"
    full = client.get(url)
    assert full.status_code == 200 and full.content == content
    assert full.headers["content-type"] == "video/mp4"
    partial = client.get(url, headers={"Range": "bytes=100-199"})
    assert partial.status_code == 206 and partial.content == content[100:200]

    # A tampered blob is refused rather than served.
    _, blob = store.open_verified(streamed.artifact_id)
    blob.write_bytes(b"tampered")
    assert client.get(url).status_code == 409
    assert store.verify_integrity(streamed.artifact_id) is False



def test_execution_workspace_files_are_listed_and_readable(
    client, db_session, monkeypatch, tmp_path
):
    monkeypatch.setenv("AGENTFORGE_DATA_DIR", str(tmp_path / "agentforge-data"))
    monkeypatch.setattr(executions_v2, "SessionLocal", lambda: db_session)

    project = models.Project(name="workspace API project")
    agent = models.Agent(project=project, name="workspace API agent")
    db_session.add_all([project, agent])
    db_session.commit()
    execution = models.Execution(
        id="workspace-api-run",
        project_id=project.id,
        root_agent_id=agent.id,
        input_task="Create a file",
        status="completed",
    )
    db_session.add(execution)
    db_session.commit()

    from app.infra.workspace import RunWorkspace
    workspace = RunWorkspace(execution.id)
    target = workspace.resolve("src/main.py")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("print('hello')", encoding="utf-8")

    listed = client.get(f"/v2/executions/{execution.id}/files")
    assert listed.status_code == 200
    assert listed.json()["files"] == [{"path": "src/main.py", "size_bytes": 14}]

    read = client.get(f"/v2/executions/{execution.id}/files/src/main.py")
    assert read.status_code == 200
    assert read.text == "print('hello')"

    preview_status = client.get(f"/v2/executions/{execution.id}/preview")
    assert preview_status.status_code == 200
    assert preview_status.json()["status"] == "stopped"
    invalid_preview = client.post(
        f"/v2/executions/{execution.id}/preview",
        json={"package_path": "src/main.py"},
    )
    assert invalid_preview.status_code == 422

    traversal = client.get(f"/v2/executions/{execution.id}/files/../outside.txt")
    assert traversal.status_code in {404, 307}
