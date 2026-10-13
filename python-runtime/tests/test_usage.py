from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app import models


def _project_agent(db_session):
    project = models.Project(name="Usage aggregation")
    agent = models.Agent(
        project=project,
        name="Usage Agent",
        provider="openai",
        model="gpt-test",
    )
    db_session.add_all([project, agent])
    db_session.commit()
    return project, agent


def test_usage_aggregates_project_cost_tokens_and_groups(client, db_session):
    project, agent = _project_agent(db_session)
    snapshot = {
        "root_id": agent.id,
        "agents": {
            agent.id: {
                "id": agent.id,
                "name": agent.name,
                "provider": agent.provider,
                "model": agent.model,
            }
        },
    }
    db_session.add_all([
        models.Execution(
            id=str(uuid4()),
            project_id=project.id,
            root_agent_id=agent.id,
            input_task="one",
            status="completed",
            started_at=datetime.now(timezone.utc) - timedelta(hours=3),
            totals={"llm_calls": 3, "tool_calls": 2, "input_tokens": 100, "output_tokens": 25, "cost_usd": 0.12},
            agent_graph_snapshot=snapshot,
        ),
        models.Execution(
            id=str(uuid4()),
            project_id=project.id,
            root_agent_id=agent.id,
            input_task="two",
            status="error",
            started_at=datetime.now(timezone.utc) - timedelta(hours=1),
            totals={"llm_calls": 1, "tool_calls": 1, "input_tokens": 20, "output_tokens": 5, "cost_usd": 0.03},
            agent_graph_snapshot=snapshot,
        ),
    ])
    db_session.commit()

    response = client.get(f"/v2/usage?project_id={project.id}&days=7")
    assert response.status_code == 200
    report = response.json()
    assert report["totals"]["runs"] == 2
    assert report["totals"]["completed_runs"] == 1
    assert report["totals"]["failed_runs"] == 1
    assert report["totals"]["llm_calls"] == 4
    assert report["totals"]["tool_calls"] == 3
    assert report["totals"]["input_tokens"] == 120
    assert report["totals"]["output_tokens"] == 30
    assert report["totals"]["cost_usd"] == 0.15
    assert report["by_agent"][0]["agent_name"] == "Usage Agent"
    assert report["by_model"][0]["model"] == "openai/gpt-test"
    assert len(report["by_day"]) == 1


def test_usage_preserves_unknown_cost_as_null(client, db_session):
    project, agent = _project_agent(db_session)
    db_session.add(models.Execution(
        id=str(uuid4()),
        project_id=project.id,
        root_agent_id=agent.id,
        input_task="unknown model pricing",
        status="completed",
        started_at=datetime.now(timezone.utc) - timedelta(hours=2),
        totals={"llm_calls": 1, "input_tokens": 12, "output_tokens": 6, "cost_usd": None},
        agent_graph_snapshot={},
    ))
    db_session.commit()

    response = client.get(f"/v2/usage?project_id={project.id}")
    assert response.status_code == 200
    report = response.json()
    assert report["totals"]["cost_usd"] is None
    assert report["by_agent"][0]["cost_usd"] is None
    assert report["by_model"][0]["cost_usd"] is None


def test_usage_rejects_invalid_period_and_unknown_project(client):
    assert client.get("/v2/usage?project_id=not-found").status_code == 404
    assert client.get("/v2/usage?project_id=not-found&days=0").status_code == 422
