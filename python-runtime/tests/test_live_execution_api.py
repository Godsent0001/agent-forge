from __future__ import annotations

from uuid import uuid4

from app import models
from app.routers import executions_v2


def _running_execution(db_session):
    project = models.Project(name="Live instructions")
    db_session.add(project)
    db_session.flush()
    agent = models.Agent(project_id=project.id, name="Builder")
    db_session.add(agent)
    db_session.flush()
    conversation = models.Conversation(
        project_id=project.id,
        agent_id=agent.id,
        title="Build task",
    )
    execution = models.Execution(
        id=str(uuid4()),
        project_id=project.id,
        root_agent_id=agent.id,
        input_task="Build an application",
        status="running",
    )
    db_session.add_all([conversation, execution])
    db_session.commit()
    return execution, conversation


def test_new_execution_carries_its_conversation_id_into_runner_request(
    client, db_session, monkeypatch
):
    project = models.Project(name="Conversation binding")
    db_session.add(project)
    db_session.flush()
    agent = models.Agent(project_id=project.id, name="Builder")
    db_session.add(agent)
    db_session.flush()
    conversation = models.Conversation(
        project_id=project.id,
        agent_id=agent.id,
        title="Active build",
    )
    db_session.add(conversation)
    db_session.commit()
    monkeypatch.setattr(executions_v2, "SessionLocal", lambda: db_session)
    captured = {}

    def capture(req):
        captured["req"] = req
        return {"id": req.execution_id, "status": "running"}

    monkeypatch.setattr(executions_v2.manager, "start", capture)
    response = client.post(
        "/v2/executions",
        json={
            "project_id": project.id,
            "root_agent_id": agent.id,
            "conversation_id": conversation.id,
            "task": "Build a web application",
        },
    )

    assert response.status_code == 200, response.text
    assert captured["req"].conversation_id == conversation.id


def test_live_instruction_is_persisted_and_delivered_to_active_execution(
    client, db_session, monkeypatch
):
    execution, conversation = _running_execution(db_session)
    execution_id = execution.id
    conversation_id = conversation.id
    monkeypatch.setattr(executions_v2, "SessionLocal", lambda: db_session)
    delivered = []
    monkeypatch.setattr(
        executions_v2.manager,
        "send_message",
        lambda execution_id, content: delivered.append((execution_id, content)) or True,
    )

    response = client.post(
        f"/v2/executions/{execution_id}/messages",
        json={
            "conversation_id": conversation_id,
            "content": "Use PostgreSQL instead of MongoDB.",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["message"]["execution_id"] == execution_id
    assert delivered == [(execution_id, "Use PostgreSQL instead of MongoDB.")]

    saved = db_session.query(models.ConversationMessage).filter_by(
        execution_id=execution_id
    ).one()
    assert saved.role == "user"
    assert saved.content == "Use PostgreSQL instead of MongoDB."


def test_live_instruction_rejects_a_conversation_from_another_agent(
    client, db_session, monkeypatch
):
    execution, _ = _running_execution(db_session)
    other_agent = models.Agent(project_id=execution.project_id, name="Other agent")
    db_session.add(other_agent)
    db_session.flush()
    other_conversation = models.Conversation(
        project_id=execution.project_id,
        agent_id=other_agent.id,
        title="Different agent",
    )
    db_session.add(other_conversation)
    db_session.commit()
    monkeypatch.setattr(executions_v2, "SessionLocal", lambda: db_session)

    response = client.post(
        f"/v2/executions/{execution.id}/messages",
        json={"conversation_id": other_conversation.id, "content": "Change the plan."},
    )
    assert response.status_code == 404


def test_individual_tool_stop_does_not_use_whole_execution_cancel(
    client, db_session, monkeypatch
):
    execution, _ = _running_execution(db_session)
    monkeypatch.setattr(executions_v2, "SessionLocal", lambda: db_session)
    stopped = []
    monkeypatch.setattr(
        executions_v2.manager,
        "stop_tool",
        lambda execution_id, tool_call_id: stopped.append((execution_id, tool_call_id)) or True,
    )

    response = client.post(
        f"/v2/executions/{execution.id}/tools/tool-call-123/cancel"
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "stopping"
    assert stopped == [(execution.id, "tool-call-123")]
