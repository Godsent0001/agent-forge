from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from app import models
from app.services import plan_intelligence, task_memory




def test_interpreter_can_create_multiple_hierarchy_levels_in_one_update(db_session, monkeypatch):
    task = _task(db_session)
    monkeypatch.setattr(task_memory, "project_dir", lambda _project_id: __import__("pathlib").Path("/tmp/agentforge-plan-tests"))
    Session = sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False)
    monkeypatch.setattr(plan_intelligence, "SessionLocal", Session)

    plan_intelligence._apply_interpretation(
        task.id,
        {
            "summary": "Created a nested execution plan.",
            "nodes": [
                {
                    "ref": "phase_design",
                    "type": "phase",
                    "title": "Design the platform",
                    "objective": "Establish the architecture.",
                    "parent_ref": "root",
                    "source": "agent",
                },
                {
                    "ref": "task_schema",
                    "type": "task",
                    "title": "Design the database schema",
                    "objective": "Define core tables and indexes.",
                    "parent_ref": "phase_design",
                    "source": "agent",
                },
                {
                    "ref": "subtask_indexes",
                    "type": "subgoal",
                    "title": "Define indexes",
                    "objective": "Specify query-critical indexes.",
                    "parent_ref": "task_schema",
                    "source": "agent",
                },
            ],
            "decisions": [],
            "constraints": [],
        },
        "Please create a plan for the platform.",
    )

    db_session.expire_all()
    plan = db_session.get(models.TaskState, task.id).state_json["plan"]
    assert len(plan["nodes"]) == 3
    by_title = {node["title"]: node for node in plan["nodes"]}
    assert by_title["Design the platform"]["parent_id"] == task.id
    assert by_title["Design the database schema"]["parent_id"] == by_title["Design the platform"]["id"]
    assert by_title["Define indexes"]["parent_id"] == by_title["Design the database schema"]["id"]
