import pytest
from fastapi import BackgroundTasks
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.db import Base
from app.routers.executions import _run_execution_in_background, run_execution, RunRequest


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


@pytest.mark.asyncio
async def test_execution_post_queues_work_and_returns_running(db_session):
    project = models.Project(name="Test Project")
    agent = models.Agent(
        project=project,
        name="Test Agent",
        provider="openai",
        model="test-model",
    )
    db_session.add_all([project, agent])
    db_session.commit()

    background_tasks = BackgroundTasks()
    result = await run_execution(
        RunRequest(
            project_id=project.id,
            root_agent_id=agent.id,
            task="Long running test",
        ),
        background_tasks,
        db_session,
    )

    assert result.status == "running"
    assert result.completed_at is None
    assert len(background_tasks.tasks) == 1
    assert background_tasks.tasks[0].func is _run_execution_in_background
    assert background_tasks.tasks[0].args[0] == result.id

    persisted = db_session.get(models.Execution, result.id)
    assert persisted is not None
    assert persisted.status == "running"
