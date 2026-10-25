from app.tools.catalog import CATALOG
from app.tools.registry import known_tool_kinds


def _project(client, name="P"):
    return client.post("/projects", json={"name": name}).json()["id"]


def _agent(client, project_id, name="A"):
    response = client.post("/agents", json={"project_id": project_id, "name": name})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _tool(client, project_id, kind="web_search"):
    response = client.post("/tools", json={"project_id": project_id, "name": kind, "kind": kind})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_every_catalog_kind_can_be_created():
    assert {entry.kind for entry in CATALOG} <= known_tool_kinds()
    assert {"custom_http", "agentforge_control", "knowledge_search"} <= known_tool_kinds()


def test_tool_creation_validates_kind_and_project(client):
    project_id = _project(client)
    assert client.post("/tools", json={"project_id": project_id, "name": "x", "kind": "not_a_tool"}).status_code == 422
    assert client.post("/tools", json={"project_id": "missing", "name": "x", "kind": "web_search"}).status_code == 404
    _tool(client, project_id, "clip_finder")


def test_agent_creation_requires_existing_project(client):
    assert client.post("/agents", json={"project_id": "missing", "name": "A"}).status_code == 404


def test_attach_tool_rejects_missing_and_cross_project_tools(client):
    first, second = _project(client, "one"), _project(client, "two")
    agent = _agent(client, first)
    foreign_tool = _tool(client, second)
    own_tool = _tool(client, first)

    assert client.post("/agents/attach-tool", json={"agent_id": agent, "tool_id": foreign_tool}).status_code == 404
    assert client.post("/agents/attach-tool", json={"agent_id": agent, "tool_id": "missing"}).status_code == 404
    assert client.post("/agents/attach-tool", json={"agent_id": "missing", "tool_id": own_tool}).status_code == 404
    ok = client.post("/agents/attach-tool", json={"agent_id": agent, "tool_id": own_tool})
    assert ok.status_code == 200 and ok.json()["attached"] is True
    assert client.get(f"/agents/{agent}").json()["tool_ids"] == [own_tool]


def test_attach_child_agent_rejects_cross_project_and_cycles(client):
    first, second = _project(client, "one"), _project(client, "two")
    parent, child = _agent(client, first, "parent"), _agent(client, first, "child")
    foreign = _agent(client, second, "foreign")

    body = {"parent_agent_id": parent, "child_agent_id": foreign}
    assert client.post("/agents/attach-child-agent", json=body).status_code == 404
    body = {"parent_agent_id": parent, "child_agent_id": "missing"}
    assert client.post("/agents/attach-child-agent", json=body).status_code == 404

    body = {"parent_agent_id": parent, "child_agent_id": child}
    assert client.post("/agents/attach-child-agent", json=body).status_code == 200
    body = {"parent_agent_id": child, "child_agent_id": parent}
    assert client.post("/agents/attach-child-agent", json=body).status_code == 400
