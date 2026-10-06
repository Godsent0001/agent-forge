import asyncio
import time
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from app import models
from app.db import Base
from app.services import executions as executions_service
from app.services.executions import ExecutionManager
from app.contracts.run import RunOptions, RunRequest


@pytest.fixture()
def test_session_factory(monkeypatch):
    engine = create_engine(
        f"sqlite:///file:execution_test_{uuid4().hex}?mode=memory&cache=shared&uri=true",
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

    db = factory()
    events = db.execute(
        select(models.ExecutionEventRow)
        .where(models.ExecutionEventRow.execution_id == req.execution_id)
        .order_by(models.ExecutionEventRow.seq)
    ).scalars().all()
    db.close()

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
