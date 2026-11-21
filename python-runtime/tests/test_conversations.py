from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app import models
from app.routers import conversations


def _project_agent(db_session):
    project = models.Project(name="Conversation tests")
    agent = models.Agent(project=project, name="Conversation agent", provider="fake", model="fake/demo")
    db_session.add_all([project, agent])
    db_session.commit()
    return project, agent


def test_conversation_persists_messages_feedback_and_title(client, db_session, monkeypatch):
    project, agent = _project_agent(db_session)
    monkeypatch.setattr(
        conversations, "_generate_conversation_title",
        lambda _db, _conversation, _content: "Ship Feature Release",
    )
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
    titled = client.post(f"/v2/conversations/{conversation['id']}/title")
    assert titled.status_code == 200
    assert titled.json()["title"] == "Ship Feature Release"

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
    assert listing.json()[0]["title"] == "Ship Feature Release"


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


def test_editing_user_message_truncates_later_turns_and_updates_title(client, db_session, monkeypatch):
    project, agent = _project_agent(db_session)
    monkeypatch.setattr(
        conversations, "_generate_conversation_title",
        lambda _db, _conversation, content: "Revised Question" if "Revised" in content else "Old Question",
    )
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
    titled = client.post(f"/v2/conversations/{conversation['id']}/title")
    assert titled.status_code == 200
    assert titled.json()["title"] == "Revised Question"

    messages = client.get(f"/v2/conversations/{conversation['id']}/messages").json()
    assert [(message["role"], message["content"]) for message in messages] == [
        ("user", "Revised question")
    ]
    listing = client.get(f"/v2/conversations?project_id={project.id}&agent_id={agent.id}").json()
    assert listing[0]["title"] == "Revised Question"


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


def test_conversation_titles_are_unique_within_agent_scope(client, db_session):
    project, agent = _project_agent(db_session)
    first = client.post(
        "/v2/conversations",
        json={"project_id": project.id, "agent_id": agent.id, "title": "Payment Architecture"},
    )
    second = client.post(
        "/v2/conversations",
        json={"project_id": project.id, "agent_id": agent.id, "title": "payment architecture"},
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["title"] == "Payment Architecture"
    assert second.json()["title"] == "payment architecture (2)"


def test_fallback_conversation_title_is_shorter_than_full_message():
    message = "Please investigate why the payment reconciliation workflow fails every night and propose a reliable fix."
    title = conversations._fallback_conversation_title(message)
    assert len(title) <= 60
    assert title != message
    assert len(title.split()) <= 8


def test_conversation_title_uses_agent_model_and_deduplicates(db_session, monkeypatch):
    project, agent = _project_agent(db_session)
    agent.provider = "openai"
    agent.model = "gpt-4o-mini"
    db_session.commit()
    calls = []

    async def fake_complete(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text="Payment Reconciliation Flow")

    monkeypatch.setattr(conversations, "adapter_complete", fake_complete)
    first = models.Conversation(project_id=project.id, agent_id=agent.id, title="New conversation")
    db_session.add(first)
    db_session.commit()
    second = models.Conversation(project_id=project.id, agent_id=agent.id, title="New conversation")
    db_session.add(second)
    db_session.commit()

    first_title = conversations._generate_conversation_title(
        db_session, first, "Please help me investigate our nightly payment reconciliation failures."
    )
    first.title = first_title
    db_session.commit()
    second_title = conversations._generate_conversation_title(
        db_session, second, "Please help me investigate a similar reconciliation problem."
    )

    assert first_title == "Payment Reconciliation Flow"
    assert second_title == "Payment Reconciliation Flow (2)"
    assert calls[0]["model"] == "openai/gpt-4o-mini"
    assert calls[0]["params"].max_tokens == 40
