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
