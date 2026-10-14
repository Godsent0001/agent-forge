from app import models
from app.contracts.run import RunRequest as CoreRunRequest
from app.routers import executions


def test_legacy_execution_endpoint_delegates_to_runner_core(client, db_session, monkeypatch):
    project = models.Project(name="legacy API project")
    agent = models.Agent(project=project, name="core agent")
    db_session.add_all([project, agent])
    db_session.commit()
    calls = []

    def start(request):
        calls.append(request)
        db_session.add(models.Execution(
            id=request.execution_id,
            project_id=request.project_id,
            root_agent_id=request.root_agent_id,
            input_task=request.task,
            status="running",
        ))
        db_session.commit()
        return {"id": request.execution_id, "status": "running"}

    monkeypatch.setattr(executions.core_execution_manager, "start", start)
    response = client.post("/executions", json={
        "project_id": project.id,
        "root_agent_id": agent.id,
        "task": "Use RunnerCore",
    })

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["project_id"] == project.id
    assert body["root_agent_id"] == agent.id
    assert body["input_task"] == "Use RunnerCore"
    assert body["status"] == "running"
    assert len(calls) == 1
    assert isinstance(calls[0], CoreRunRequest)
    assert calls[0].project_id == project.id
    assert calls[0].root_agent_id == agent.id
    assert calls[0].task == "Use RunnerCore"
