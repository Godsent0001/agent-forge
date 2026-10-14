import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.db import Base
from app.routers import executions
from app.routers.executions import RunRequest, run_execution


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.mark.asyncio
async def test_execution_post_delegates_to_runner_core_and_returns_running(db_session, monkeypatch):
    project = models.Project(name="Test Project")
    agent = models.Agent(
        project=project,
        name="Test Agent",
        provider="openai",
        model="test-model",
    )
    db_session.add_all([project, agent])
    db_session.commit()
    captured = []

    def start(request):
        captured.append(request)
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
    result = await run_execution(
        RunRequest(
            project_id=project.id,
            root_agent_id=agent.id,
            task="Long running test",
        ),
        db_session,
    )

    assert result.status == "running"
    assert result.completed_at is None
    assert len(captured) == 1
    assert captured[0].project_id == project.id
    assert captured[0].root_agent_id == agent.id
    assert captured[0].task == "Long running test"

    persisted = db_session.get(models.Execution, result.id)
    assert persisted is not None
    assert persisted.status == "running"
