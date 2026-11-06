from __future__ import annotations

from uuid import uuid4

from app import models


def _project_agent(db_session):
    project = models.Project(name="Conversation tests")
    agent = models.Agent(project=project, name="Conversation agent", provider="fake", model="fake/demo")
    db_session.add_all([project, agent])
    db_session.commit()
    return project, agent


def test_conversation_persists_messages_feedback_and_title(client, db_session):
    project, agent = _project_agent(db_session)
    created = client.post("/v2/conversations", json={"project_id": project.id, "agent_id": agent.id})
    assert created.status_code == 200
    conversation = created.json()
    assert conversation["title"] == "New conversation"

    user = client.post(
        f"/v2/conversations/{conversation['id']}/messages",
        json={"role": "user", "content": "  Help me ship the feature  "},
    )
    assert user.status_code == 200
    assert user.json()["role"] == "user"
    assert user.json()["content"] == "  Help me ship the feature  "

    execution = models.Execution(
        id=str(uuid4()),
        project_id=project.id,
        root_agent_id=agent.id,
        input_task="Help me ship the feature",
        status="completed",
        final_output="Let's ship it.",
    )
    db_session.add(execution)
    db_session.commit()
    assistant = client.post(
        f"/v2/conversations/{conversation['id']}/messages",
        json={"role": "assistant", "content": "Let's ship it.", "execution_id": execution.id},
    )
    assert assistant.status_code == 200
    message_id = assistant.json()["id"]

    feedback = client.put(
        f"/v2/messages/{message_id}/feedback",
        json={"value": 1, "note": "Useful"},
    )
    assert feedback.status_code == 200
    update = client.put(
        f"/v2/messages/{message_id}/feedback",
        json={"value": -1, "note": "Not quite"},
    )
    assert update.status_code == 200

    messages = client.get(f"/v2/conversations/{conversation['id']}/messages")
    assert messages.status_code == 200
    assert [message["role"] for message in messages.json()] == ["user", "assistant"]
    assert messages.json()[1]["feedback_value"] == -1
    assert messages.json()[1]["feedback_note"] == "Not quite"
    assert messages.json()[0]["execution_status"] is None
    assert messages.json()[1]["execution_status"] == "completed"
    assert assistant.json()["execution_status"] == "completed"

    listing = client.get(f"/v2/conversations?project_id={project.id}&agent_id={agent.id}")
    assert listing.status_code == 200
    assert len(listing.json()) == 1
    assert listing.json()[0]["title"] == "Help me ship the feature"


def test_conversation_cannot_cross_project_or_attach_foreign_execution(client, db_session):
    project, agent = _project_agent(db_session)
    other_project, other_agent = _project_agent(db_session)
    rejected = client.post(
        "/v2/conversations",
        json={"project_id": project.id, "agent_id": other_agent.id},
    )
    assert rejected.status_code == 404

    created = client.post("/v2/conversations", json={"project_id": project.id, "agent_id": agent.id}).json()
    foreign_execution = models.Execution(
        id=str(uuid4()),
        project_id=other_project.id,
        root_agent_id=other_agent.id,
        input_task="foreign",
        status="completed",
    )
    db_session.add(foreign_execution)
    db_session.commit()
    response = client.post(
        f"/v2/conversations/{created['id']}/messages",
        json={"role": "assistant", "content": "bad link", "execution_id": foreign_execution.id},
    )
    assert response.status_code == 404


def test_feedback_only_accepts_assistant_messages(client, db_session):
    project, agent = _project_agent(db_session)
    conversation = client.post(
        "/v2/conversations", json={"project_id": project.id, "agent_id": agent.id}
    ).json()
    user = client.post(
        f"/v2/conversations/{conversation['id']}/messages",
        json={"role": "user", "content": "A question"},
    ).json()
    assert client.put(f"/v2/messages/{user['id']}/feedback", json={"value": 1}).status_code == 422


def test_editing_user_message_truncates_later_turns_and_updates_title(client, db_session):
    project, agent = _project_agent(db_session)
    conversation = client.post(
        "/v2/conversations", json={"project_id": project.id, "agent_id": agent.id}
    ).json()
    first = client.post(
        f"/v2/conversations/{conversation['id']}/messages",
        json={"role": "user", "content": "Old question"},
    ).json()
    execution = models.Execution(
        id=str(uuid4()),
        project_id=project.id,
        root_agent_id=agent.id,
        input_task="Old question",
        status="completed",
        final_output="Old answer",
    )
    db_session.add(execution)
    db_session.commit()
    client.post(
        f"/v2/conversations/{conversation['id']}/messages",
        json={"role": "assistant", "content": "Old answer", "execution_id": execution.id},
    )
    client.post(
        f"/v2/conversations/{conversation['id']}/messages",
        json={"role": "user", "content": "Follow-up"},
    )

    edited = client.patch(
        f"/v2/messages/{first['id']}",
        json={"content": "  Revised question  "},
    )
    assert edited.status_code == 200
    assert edited.json()["content"] == "Revised question"

    messages = client.get(f"/v2/conversations/{conversation['id']}/messages").json()
    assert [(message["role"], message["content"]) for message in messages] == [
        ("user", "Revised question")
    ]
    listing = client.get(f"/v2/conversations?project_id={project.id}&agent_id={agent.id}").json()
    assert listing[0]["title"] == "Revised question"


def test_editing_assistant_message_is_rejected(client, db_session):
    project, agent = _project_agent(db_session)
    conversation = client.post(
        "/v2/conversations", json={"project_id": project.id, "agent_id": agent.id}
    ).json()
    execution = models.Execution(
        id=str(uuid4()),
        project_id=project.id,
        root_agent_id=agent.id,
        input_task="Question",
        status="completed",
        final_output="Answer",
    )
    db_session.add(execution)
    db_session.commit()
    assistant = client.post(
        f"/v2/conversations/{conversation['id']}/messages",
        json={"role": "assistant", "content": "Answer", "execution_id": execution.id},
    ).json()
    response = client.patch(
        f"/v2/messages/{assistant['id']}",
        json={"content": "Edited answer"},
    )
    assert response.status_code == 422
