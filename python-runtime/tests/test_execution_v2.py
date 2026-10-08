import asyncio
import time
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from app import models
from app.contracts.run import RunOptions, RunRequest
from app.db import Base
from app.services import executions as executions_service
from app.services.executions import ExecutionManager


@pytest.fixture()
def test_session_factory(monkeypatch):
    engine = create_engine(
        f"sqlite:///file:execution_test_{uuid4().hex}?mode=memory&cache=shared&uri=true",
        connect_args={"check_same_thread": False},
        poolclass=QueuePool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(executions_service, "SessionLocal", factory)
    db = factory()
    project = models.Project(name="test")
    agent = models.Agent(project=project, name="Test Agent")
    db.add_all([project, agent])
    db.commit()
    ids = (project.id, agent.id)
    db.close()
    try:
        yield factory, ids
    finally:
        engine.dispose()


async def wait_for_terminal(factory, execution_id):
    for _ in range(250):
        db = factory()
        row = db.get(models.Execution, execution_id)
        db.close()
        if row and row.status != "running":
            return row
        await asyncio.sleep(0.02)
    raise AssertionError("execution did not reach a terminal state")


async def wait_for_events(factory, execution_id):
    for _ in range(250):
        db = factory()
        events = db.execute(
            select(models.ExecutionEventRow)
            .where(models.ExecutionEventRow.execution_id == execution_id)
            .order_by(models.ExecutionEventRow.seq)
        ).scalars().all()
        db.close()
        if events and events[-1].type == "execution_ended":
            return events
        await asyncio.sleep(0.02)
    raise AssertionError("execution_ended event was not persisted")


@pytest.mark.asyncio
async def test_slow_post_path_returns_immediately_and_trace_is_sequenced(test_session_factory):
    factory, (project_id, agent_id) = test_session_factory
    manager = ExecutionManager()
    req = RunRequest(
        execution_id=str(uuid4()),
        project_id=project_id,
        root_agent_id=agent_id,
        task="slow task",
        options=RunOptions(scenario="sleep_3s"),
    )

    started = time.perf_counter()
    response = manager.start(req)
    elapsed = time.perf_counter() - started

    assert elapsed < 0.2
    assert response["status"] == "running"

    row = await wait_for_terminal(factory, req.execution_id)
    assert row.status == "completed"

    events = await wait_for_events(factory, req.execution_id)

    assert [event.seq for event in events] == list(range(1, len(events) + 1))
    assert events[0].type == "execution_started"
    assert events[-1].type == "execution_ended"
    await manager.shutdown()


@pytest.mark.asyncio
async def test_cancel_closes_agent_span(test_session_factory):
    factory, (project_id, agent_id) = test_session_factory
    manager = ExecutionManager()
    req = RunRequest(
        execution_id=str(uuid4()),
        project_id=project_id,
        root_agent_id=agent_id,
        task="cancel me",
        options=RunOptions(scenario="sleep_3s"),
    )
    manager.start(req)
    await asyncio.sleep(0.05)
    assert await manager.cancel(req.execution_id)

    row = await wait_for_terminal(factory, req.execution_id)
    assert row.status == "cancelled"

    db = factory()
    events = db.execute(
        select(models.ExecutionEventRow)
        .where(models.ExecutionEventRow.execution_id == req.execution_id)
        .order_by(models.ExecutionEventRow.seq)
    ).scalars().all()
    db.close()

    assert events[-1].type == "execution_ended"
    span_ends = [event for event in events if event.type == "span_ended"]
    assert span_ends
    assert any(event.status == "cancelled" for event in span_ends)
    await manager.shutdown()


@pytest.mark.asyncio
async def test_v2_runner_wires_graph_workspace_and_fake_llm(test_session_factory, monkeypatch):
    factory, (project_id, agent_id) = test_session_factory

    from app.core.llm.fake import FakeLLM
    from app.core.llm.types import LLMTurn
    from app.core.runner import RunnerCore

    monkeypatch.setattr(
        executions_service,
        "get_runner",
        lambda: RunnerCore(fake_llm=FakeLLM([
            LLMTurn(text="v2 integration answer"),
        ])),
    )

    manager = ExecutionManager()
    req = RunRequest(
        execution_id=str(uuid4()),
        project_id=project_id,
        root_agent_id=agent_id,
        task="exercise the v2 runner",
    )

    response = manager.start(req)
    assert response == {"id": req.execution_id, "status": "running"}

    row = await wait_for_terminal(factory, req.execution_id)
    assert row.status == "completed"
    assert row.final_output == "v2 integration answer"

    db = factory()
    events = db.execute(
        select(models.ExecutionEventRow)
        .where(models.ExecutionEventRow.execution_id == req.execution_id)
        .order_by(models.ExecutionEventRow.seq)
    ).scalars().all()
    db.close()

    assert events[0].type == "execution_started"
    assert events[-1].type == "execution_ended"

    spans = [event for event in events if event.type == "span_started"]
    assert [event.kind for event in spans] == ["agent", "llm_call"]

    ended_spans = {event.span_id: event for event in events if event.type == "span_ended"}
    assert all(event.span_id in ended_spans for event in spans)
    assert all(event.status == "ok" for event in ended_spans.values())

    await manager.shutdown()


def test_startup_cleanup_marks_stale_running_execution_interrupted(test_session_factory):
    factory, (project_id, agent_id) = test_session_factory
    db = factory()
    execution = models.Execution(
        id=str(uuid4()),
        project_id=project_id,
        root_agent_id=agent_id,
        input_task="stale run",
        status="running",
        agent_graph_snapshot={},
    )
    db.add(execution)
    db.commit()
    execution_id = execution.id
    db.close()

    manager = ExecutionManager()
    assert manager.mark_running_interrupted() == 1

    db = factory()
    row = db.get(models.Execution, execution_id)
    db.close()

    assert row.status == "interrupted"
    assert row.ended_at is not None


def _build_test_api(monkeypatch, factory):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.routers import executions_v2

    manager = ExecutionManager()
    monkeypatch.setattr(executions_service, "SessionLocal", factory)
    monkeypatch.setattr(executions_v2, "SessionLocal", factory)
    monkeypatch.setattr(executions_v2, "manager", manager)

    app = FastAPI()
    app.include_router(executions_v2.router)
    client = TestClient(app)
    client.__enter__()
    return client, manager


def test_http_post_returns_immediately_and_get_reaches_terminal(test_session_factory, monkeypatch):
    factory, (project_id, agent_id) = test_session_factory
    client, manager = _build_test_api(monkeypatch, factory)
    monkeypatch.setattr(manager, 'shutdown', lambda: None)

    started = time.perf_counter()
    response = client.post(
        "/v2/executions",
        json={
            "project_id": project_id,
            "root_agent_id": agent_id,
            "task": "slow HTTP task",
            "options": {"scenario": "sleep_3s"},
        },
    )
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "running"
    assert elapsed < 0.2

    for _ in range(180):
        detail = client.get(f"/v2/executions/{payload['id']}")
        assert detail.status_code == 200
        if detail.json()["status"] != "running":
            break
        time.sleep(0.025)
    else:
        pytest.fail("HTTP execution did not reach a terminal state")

    assert detail.json()["status"] == "completed"
    client.close()


def test_websocket_stream_replays_without_duplicates(test_session_factory, monkeypatch):
    factory, (project_id, agent_id) = test_session_factory
    client, manager = _build_test_api(monkeypatch, factory)

    response = client.post(
        "/v2/executions",
        json={
            "project_id": project_id,
            "root_agent_id": agent_id,
            "task": "trace task",
            "options": {"scenario": "tool_call"},
        },
    )
    assert response.status_code == 200
    execution_id = response.json()["id"]

    received = []
    with client.websocket_connect(f"/v2/executions/{execution_id}/stream") as websocket:
        while True:
            event = websocket.receive_json()
            received.append(event)
            if event["type"] == "execution_ended":
                break

    seqs = [event["seq"] for event in received]
    assert seqs == list(range(1, len(seqs) + 1))

    with client.websocket_connect(
        f"/v2/executions/{execution_id}/stream?after_seq=2"
    ) as websocket:
        replayed = []
        expected = [event for event in received if event["seq"] > 2]
        for _ in expected:
            replayed.append(websocket.receive_json())

    assert [event["seq"] for event in replayed] == [event["seq"] for event in expected]
    assert all(event["seq"] > 2 for event in replayed)
    client.close()
