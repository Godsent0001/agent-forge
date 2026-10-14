from __future__ import annotations

from app import models


def _agent(db_session):
    project = models.Project(name="Memory UI")
    agent = models.Agent(project=project, name="Memory agent")
    db_session.add_all([project, agent])
    db_session.commit()
    return project, agent


def test_memory_routes_create_pin_edit_archive_and_clear(client, db_session):
    _, agent = _agent(db_session)
    created = client.post(
        f"/v2/agents/{agent.id}/memory",
        json={"text": "User prefers concise answers", "kind": "preference"},
    )
    assert created.status_code == 200
    item = created.json()
    assert item["source_type"] == "user_edited"
    assert item["status"] == "active"

    pinned = client.patch(
        f"/v2/agents/{agent.id}/memory/{item['id']}", json={"pinned": True}
    )
    assert pinned.status_code == 200
    assert pinned.json()["pinned"] is True

    edited = client.patch(
        f"/v2/agents/{agent.id}/memory/{item['id']}",
        json={"text": "User likes brief replies"},
    )
    assert edited.status_code == 200
    assert edited.json()["text"] == "User likes brief replies"

    archived = client.patch(
        f"/v2/agents/{agent.id}/memory/{item['id']}", json={"status": "archived"}
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    all_items = client.get(f"/v2/agents/{agent.id}/memory")
    assert all_items.status_code == 200
    assert all_items.json()[0]["status"] == "archived"
    active_items = client.get(f"/v2/agents/{agent.id}/memory?status=active")
    assert active_items.json() == []

    cleared = client.delete(f"/v2/agents/{agent.id}/memory")
    assert cleared.status_code == 200
    assert cleared.json()["deleted"] == 1


def test_lessons_can_be_archived_restored_and_deleted(client, db_session):
    _, agent = _agent(db_session)
    created = client.post(
        f"/v2/agents/{agent.id}/lessons",
        json={"text": "Validate a path before sending it to a tool."},
    )
    assert created.status_code == 200
    lesson = created.json()
    archived = client.patch(
        f"/v2/agents/{agent.id}/lessons/{lesson['id']}",
        json={"status": "archived"},
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    restored = client.patch(
        f"/v2/agents/{agent.id}/lessons/{lesson['id']}",
        json={"status": "active"},
    )
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"
    assert client.delete(f"/v2/agents/{agent.id}/lessons/{lesson['id']}").json() == {"deleted": True}
