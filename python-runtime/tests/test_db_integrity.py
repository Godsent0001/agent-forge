from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.db import Base


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_delete_child_agent_removes_parent_links(db):
    project = models.Project(name="p")
    parent = models.Agent(project=project, name="parent")
    child = models.Agent(project=project, name="child")
    db.add_all([project, parent, child])
    db.flush()
    db.add(models.AgentAgentLink(parent_agent_id=parent.id, child_agent_id=child.id))
    db.commit()

    db.delete(child)
    db.commit()

    assert db.query(models.AgentAgentLink).count() == 0


def test_duplicate_tool_attachment_is_rejected(db):
    project = models.Project(name="p")
    agent = models.Agent(project=project, name="a")
    tool = models.Tool(project=project, name="t", kind="fake")
    db.add_all([project, agent, tool])
    db.flush()
    db.add(models.AgentToolLink(agent_id=agent.id, tool_id=tool.id))
    db.commit()
    db.add(models.AgentToolLink(agent_id=agent.id, tool_id=tool.id))

    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_foreign_key_enforcement_rejects_missing_agent(db):
    project = models.Project(name="p")
    db.add(project)
    db.commit()
    db.add(models.AgentToolLink(agent_id="missing", tool_id="missing"))

    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_project_delete_cascades_agents_tools_executions_and_events(db):
    project = models.Project(name="p")
    agent = models.Agent(project=project, name="a")
    tool = models.Tool(project=project, name="t", kind="fake")
    db.add_all([project, agent, tool])
    db.flush()

    execution = models.Execution(
        project_id=project.id,
        root_agent_id=agent.id,
        input_task="x",
        started_at=datetime.now(timezone.utc),
    )
    db.add(execution)
    db.flush()
    db.add(models.ExecutionEventRow(
        execution_id=execution.id,
        seq=1,
        type="execution_started",
        timestamp=datetime.now(timezone.utc),
    ))
    db.commit()

    db.delete(project)
    db.commit()

    assert db.query(models.Agent).count() == 0
    assert db.query(models.Tool).count() == 0
    assert db.query(models.Execution).count() == 0
    assert db.query(models.ExecutionEventRow).count() == 0
