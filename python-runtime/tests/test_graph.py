import itertools

import pytest
from app.graph import GraphValidationError, validate_new_link
from app.models import Agent, AgentAgentLink, Project

def make_project(db):
    project = Project(name="test")
    db_session.add(project)
    db_session.flush()
    return project

def make_agent(db, project, name):
    agent = Agent(project_id=project.id, name=name)
    db_session.add(agent)
    db_session.flush()
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
    db_session.add(AgentAgentLink(parent_agent_id=a.id, child_agent_id=b.id))
    db_session.flush()
    with pytest.raises(GraphValidationError):
        validate_new_link(db_session, b.id, a.id)

def test_valid_chain_accepted(db_session):
    p = make_project(db_session)
    a = make_agent(db_session, p, "A")
    b = make_agent(db_session, p, "B")
    db_session.add(AgentAgentLink(parent_agent_id=a.id, child_agent_id=b.id))
    db_session.flush()
    c = make_agent(db_session, p, "C")
    validate_new_link(db_session, b.id, c.id)

def test_depth_over_eight_rejected(db_session):
    p = make_project(db_session)
    agents = [make_agent(db_session, p, str(i)) for i in range(9)]
    for parent, child in itertools.pairwise(agents):
        db_session.add(AgentAgentLink(parent_agent_id=parent.id, child_agent_id=child.id))
    db_session.flush()
    extra = make_agent(db_session, p, "extra")
    with pytest.raises(GraphValidationError):
        validate_new_link(db_session, extra.id, agents[0].id)
