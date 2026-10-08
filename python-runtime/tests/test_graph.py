import pytest
from app.graph import GraphValidationError, validate_new_link
from app.models import Agent, AgentAgentLink, Project

def make_project(db):
    project = Project(name="test")
    db.add(project)
    db.flush()
    return project

def make_agent(db, project, name):
    agent = Agent(project_id=project.id, name=name)
    db.add(agent)
    db.flush()
    return agent

def test_self_link_rejected(db_session):
    p = make_project(db_session)
    a = make_agent(db_session, p, "A")
    with pytest.raises(GraphValidationError):
        validate_new_link(db_session, a.id, a.id)

def test_cycle_rejected(db_session):
    p = make_project(db_session)
    a = make_agent(db_session, p, "A")
    b = make_agent(db_session, p, "B")
    db.add(AgentAgentLink(parent_agent_id=a.id, child_agent_id=b.id))
    db.flush()
    with pytest.raises(GraphValidationError):
        validate_new_link(db_session, b.id, a.id)

def test_valid_chain_accepted(db_session):
    p = make_project(db_session)
    a = make_agent(db_session, p, "A")
    b = make_agent(db_session, p, "B")
    db.add(AgentAgentLink(parent_agent_id=a.id, child_agent_id=b.id))
    db.flush()
    c = make_agent(db_session, p, "C")
    validate_new_link(db_session, b.id, c.id)

def test_depth_over_eight_rejected(db_session):
    p = make_project(db_session)
    agents = [make_agent(db_session, p, str(i)) for i in range(9)]
    for parent, child in zip(agents, agents[1:]):
        db.add(AgentAgentLink(parent_agent_id=parent.id, child_agent_id=child.id))
    db.flush()
    extra = make_agent(db_session, p, "extra")
    with pytest.raises(GraphValidationError):
        validate_new_link(db_session, extra.id, agents[0].id)
