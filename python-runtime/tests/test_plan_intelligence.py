from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from app import models
from app.services import plan_intelligence, task_memory


def _task(db_session):
    project = models.Project(name="Plan memory tests")
    db_session.add(project)
    db_session.flush()
    agent = models.Agent(project_id=project.id, name="Plan agent", provider="fake", model="fake/demo")
    db_session.add(agent)
    db_session.flush()
    conversation = models.Conversation(project_id=project.id, agent_id=agent.id)
    db_session.add(conversation)
    db_session.flush()
    task = models.TaskState(
        id="plan-memory-task",
        conversation_id=conversation.id,
        project_id=project.id,
        agent_id=agent.id,
        title="Build a payment platform",
        original_objective="Build a reliable payment platform.",
        current_instruction="Build a reliable payment platform.",
        status="active",
        state_json={"constraints": [], "decisions": [], "completed": [], "remaining": [], "blockers": []},
        version=1,
    )
    db_session.add(task)
    db_session.commit()
    return task


def test_user_evidence_is_required_for_binding_plan_changes(db_session, monkeypatch):
    task = _task(db_session)
    monkeypatch.setattr(task_memory, "project_dir", lambda _project_id: Path("/tmp/agentforge-plan-tests"))
    Session = sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False)
    monkeypatch.setattr(plan_intelligence, "SessionLocal", Session)

    result = plan_intelligence._apply_interpretation(
        task.id,
        {
            "summary": "Captured the user's initial design.",
            "root_summary": "Build a reliable payment platform with PostgreSQL.",
            "nodes": [
                {
                    "type": "phase",
                    "title": "Use PostgreSQL",
                    "objective": "Build the persistence layer.",
                    "parent_ref": "root",
                    "source": "user",
                    "evidence": "Use PostgreSQL for the primary database.",
                },
                {
                    "type": "phase",
                    "title": "Invented requirement",
                    "objective": "Not actually requested.",
                    "parent_ref": "root",
                    "source": "user",
                    "evidence": "Use MongoDB.",
                },
            ],
            "decisions": [
                {
                    "text": "Use PostgreSQL for the primary database.",
                    "authority": "user",
                    "evidence": "Use PostgreSQL for the primary database.",
                }
            ],
            "constraints": [
                {
                    "text": "Use PostgreSQL for the primary database.",
                    "evidence": "Use PostgreSQL for the primary database.",
                }
            ],
        },
        "Use PostgreSQL for the primary database.",
    )

    db_session.expire_all()
    updated = db_session.get(models.TaskState, task.id)
    plan = updated.state_json["plan"]
    assert result["applied"] is True
    assert len(plan["nodes"]) == 1
    assert plan["nodes"][0]["status"] == "active"
    assert plan["decisions"][0]["status"] == "accepted"
    assert len(plan["constraints"]) == 1
    assert plan["root_summary"] == "Build a reliable payment platform with PostgreSQL."

    event = db_session.query(models.TaskStateEvent).filter_by(
        task_state_id=task.id, event_type="plan_memory_updated"
    ).one()
    assert event.payload["change_count"] == 4
    assert len(event.payload["changes"]) == 4

    updated.state_json = {**updated.state_json, "plan": {}}
    db_session.commit()
    rebuilt = plan_intelligence.rebuild_plan_from_history(task.id)
    db_session.expire_all()
    restored = db_session.get(models.TaskState, task.id).state_json["plan"]
    assert rebuilt["rebuilt"] is True
    assert rebuilt["events_replayed"] >= 1
    assert len(restored["nodes"]) == 1
    assert restored["decisions"][0]["status"] == "accepted"
    assert len(restored["constraints"]) == 1
    assert restored["root_summary"] == "Build a reliable payment platform with PostgreSQL."


def test_agent_plan_is_kept_separate_from_accepted_user_decisions(db_session, monkeypatch):
    task = _task(db_session)
    monkeypatch.setattr(task_memory, "project_dir", lambda _project_id: Path("/tmp/agentforge-plan-tests"))
    Session = sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False)
    monkeypatch.setattr(plan_intelligence, "SessionLocal", Session)

    plan_intelligence._apply_interpretation(
        task.id,
        {
            "summary": "Proposed an execution plan.",
            "nodes": [
                {
                    "type": "phase",
                    "title": "Design database schema",
                    "objective": "Define core entities and indexes.",
                    "parent_ref": "root",
                    "source": "agent",
                    "evidence": "",
                }
            ],
            "decisions": [
                {
                    "text": "Use Redis for caching.",
                    "authority": "user",
                    "evidence": "User said Redis is approved.",
                }
            ],
            "constraints": [],
        },
        "Actually, investigate caching options first.",
    )

    db_session.expire_all()
    updated = db_session.get(models.TaskState, task.id)
    plan = updated.state_json["plan"]
    assert plan["nodes"][0]["source"] == "agent"
    assert plan["nodes"][0]["status"] == "active"
    assert plan["decisions"][0]["status"] == "proposed"
    context = plan_intelligence.compile_plan_context(task.id)
    assert "Design database schema" in context
    assert "Unaccepted agent/user proposals" in context
    assert "Accepted user decisions" not in context


def test_plan_context_preserves_nested_parent_child_relationships(db_session, monkeypatch):
    task = _task(db_session)
    Session = sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False)
    monkeypatch.setattr(plan_intelligence, "SessionLocal", Session)

    root_child = {
        "id": "phase-1",
        "parent_id": task.id,
        "type": "phase",
        "title": "Persistence",
        "objective": "Build persistence foundations.",
        "status": "active",
        "source": "agent",
    }
    nested_child = {
        "id": "task-1",
        "parent_id": "phase-1",
        "type": "task",
        "title": "Create schema",
        "objective": "Create the relational schema.",
        "status": "blocked",
        "source": "agent",
    }
    with Session() as db:
        row = db.get(models.TaskState, task.id)
        row.state_json = {**row.state_json, "plan": {"nodes": [root_child, nested_child]}}
        db.commit()

    context = plan_intelligence.compile_plan_context(task.id)
    assert "Root objective excerpt: Build a reliable payment platform." in context
    assert "- [active] phase: Persistence" in context
    assert "  - [blocked] task: Create schema" in context


def test_plan_memory_settings_validate_and_persist_custom_model(tmp_path, monkeypatch):
    path = tmp_path / "plan_memory_settings.json"
    monkeypatch.setattr(plan_intelligence, "_config_path", lambda: path)

    saved = plan_intelligence.save_plan_memory_settings({
        "enabled": True,
        "provider": "openrouter",
        "model": "anthropic/claude-3.5-haiku",
    })
    assert saved == {
        "enabled": True,
        "provider": "openrouter",
        "model": "anthropic/claude-3.5-haiku",
    }
    assert json.loads(path.read_text("utf-8")) == saved
    loaded = plan_intelligence.load_plan_memory_settings()
    assert loaded["enabled"] is True
    assert loaded["provider"] == saved["provider"]
    assert loaded["model"] == saved["model"]

    try:
        plan_intelligence.save_plan_memory_settings({
            "enabled": True,
            "provider": "unsupported",
            "model": "model",
        })
    except ValueError:
        pass
    else:
        raise AssertionError("Unsupported providers must be rejected.")



def test_plan_memory_settings_api(client, monkeypatch, tmp_path):
    monkeypatch.setattr(plan_intelligence, "_config_path", lambda: tmp_path / "plan_memory_settings.json")
    initial = client.get("/settings/plan-memory")
    assert initial.status_code == 200
    assert initial.json()["enabled"] is False

    response = client.post(
        "/settings/plan-memory",
        json={"enabled": True, "provider": "gemini", "model": "gemini-2.5-flash-lite"},
    )
    assert response.status_code == 200
    assert response.json()["enabled"] is True
    assert response.json()["model"] == "gemini-2.5-flash-lite"

    invalid = client.post(
        "/settings/plan-memory",
        json={"enabled": True, "provider": "not-a-provider", "model": "bad model"},
    )
    assert invalid.status_code == 422



def test_agent_plan_status_can_follow_exact_execution_evidence(db_session, monkeypatch):
    task = _task(db_session)
    monkeypatch.setattr(task_memory, "project_dir", lambda _project_id: Path("/tmp/agentforge-plan-tests"))
    Session = sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False)
    monkeypatch.setattr(plan_intelligence, "SessionLocal", Session)
    with Session() as db:
        row = db.get(models.TaskState, task.id)
        row.state_json = {
            **row.state_json,
            "plan": {
                "nodes": [{
                    "id": "agent-task-1",
                    "parent_id": task.id,
                    "type": "task",
                    "title": "Create the database schema",
                    "status": "active",
                    "source": "agent",
                    "version": 1,
                }]
            },
        }
        db.commit()

    plan_intelligence._apply_interpretation(
        task.id,
        {
            "summary": "The schema task is blocked by a verified tool error.",
            "nodes": [],
            "node_updates": [{
                "id": "agent-task-1",
                "status": "blocked",
                "evidence": "ERROR: operation is blocked because the database is locked.",
            }],
            "decisions": [],
            "constraints": [],
        },
        "Continue with the payment platform.",
        "Tool result: ERROR: operation is blocked because the database is locked.",
    )

    db_session.expire_all()
    node = db_session.get(models.TaskState, task.id).state_json["plan"]["nodes"][0]
    assert node["status"] == "blocked"



def test_meaningful_short_design_choices_trigger_interpretation():
    assert plan_intelligence._should_interpret("Use PostgreSQL")
    assert plan_intelligence._should_interpret("Avoid Redis")
    assert not plan_intelligence._should_interpret("Hello there")
    assert not plan_intelligence._should_interpret("Thanks")



def test_optional_memory_call_reserves_primary_execution_budget():
    from types import SimpleNamespace

    budget = SimpleNamespace(
        spec=SimpleNamespace(
            max_llm_calls=1,
            max_total_tokens=None,
            max_cost_usd=None,
            max_seconds=None,
        ),
        totals=SimpleNamespace(
            llm_calls=0,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
        ),
        elapsed_seconds=0.0,
    )
    assert not plan_intelligence._budget_allows_memory_call(budget, "Plan update", 1800)



def test_working_context_prioritizes_active_and_recent_nodes(db_session, monkeypatch):
    task = _task(db_session)
    Session = sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False)
    monkeypatch.setattr(plan_intelligence, "SessionLocal", Session)
    with Session() as db:
        row = db.get(models.TaskState, task.id)
        archived = [
            {
                "id": f"archived-{index}",
                "parent_id": task.id,
                "type": "task",
                "title": f"Archived task {index}",
                "status": "completed",
                "source": "agent",
                "created_at": f"2026-01-{(index % 28) + 1:02d}T00:00:00+00:00",
                "updated_at": f"2026-01-{(index % 28) + 1:02d}T00:00:00+00:00",
            }
            for index in range(30)
        ]
        current = {
            "id": "current-task",
            "parent_id": task.id,
            "type": "phase",
            "title": "Current payment reconciliation",
            "objective": "Finish the active payment flow.",
            "status": "active",
            "source": "agent",
            "created_at": "2026-11-10T00:00:00+00:00",
            "updated_at": "2026-11-10T00:00:00+00:00",
        }
        row.state_json = {**row.state_json, "plan": {"nodes": archived + [current]}}
        db.commit()

    context = plan_intelligence.compile_plan_context(task.id)
    assert "Current payment reconciliation" in context
    assert "id=current-task" in context
    assert "Archived task 0" not in context


def test_integrity_audit_is_append_only_and_rejects_unknown_node_references(db_session, monkeypatch):
    task = _task(db_session)
    Session = sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False)
    monkeypatch.setattr(plan_intelligence, "SessionLocal", Session)
    monkeypatch.setattr(task_memory, "project_dir", lambda _project_id: Path("/tmp/agentforge-plan-tests"))
    with Session() as db:
        row = db.get(models.TaskState, task.id)
        row.state_json = {
            **row.state_json,
            "plan": {"nodes": [{
                "id": "phase-persistence", "parent_id": task.id, "type": "phase",
                "title": "Persistence", "status": "active", "source": "agent",
            }]},
        }
        db.commit()

    result = plan_intelligence._record_integrity_audit(
        task.id,
        {
            "overall": "One prerequisite concern needs review.",
            "findings": [
                {
                    "category": "prerequisite_regression", "severity": "warning",
                    "summary": "A completed task depends on a prerequisite that is no longer complete.",
                    "affected_ids": ["phase-persistence", "made-up-node"],
                    "evidence": "The dependency edge points to a superseded prerequisite.",
                },
                {
                    "category": "decision_conflict", "severity": "critical",
                    "summary": "Invented finding with no valid node reference.",
                    "affected_ids": ["made-up-node"],
                },
            ],
        },
        "gemini/gemini-2.5-flash-lite",
    )

    db_session.expire_all()
    updated = db_session.get(models.TaskState, task.id)
    audit = updated.state_json["plan"]["integrity_audit"]
    assert result["recorded"] is True
    assert result["findings"] == 1
    assert audit["findings"][0]["affected_ids"] == ["phase-persistence"]
    assert updated.original_objective == "Build a reliable payment platform."
    assert updated.state_json["plan"]["nodes"][0]["status"] == "active"
    event = db_session.query(models.TaskStateEvent).filter_by(
        task_state_id=task.id, event_type="plan_integrity_audited"
    ).one()
    assert event.payload["audit"]["findings"][0]["category"] == "prerequisite_regression"


def test_integrity_audit_is_due_initially_and_after_five_plan_updates(db_session, monkeypatch):
    task = _task(db_session)
    assert plan_intelligence._integrity_audit_due(db_session, task) is True
    now = plan_intelligence._now()
    db_session.add(models.TaskStateEvent(
        id=models._uuid(), task_state_id=task.id, event_type="plan_integrity_audited",
        content="Audit complete.", payload={}, created_at=now,
    ))
    db_session.flush()
    for index in range(3):
        db_session.add(models.TaskStateEvent(
            id=models._uuid(), task_state_id=task.id, event_type="plan_memory_updated",
            content=f"Plan update {index}.", payload={}, created_at=now,
        ))
    db_session.flush()
    assert plan_intelligence._integrity_audit_due(db_session, task) is False
    later = now + __import__("datetime").timedelta(seconds=1)
    db_session.add(models.TaskStateEvent(
        id=models._uuid(), task_state_id=task.id, event_type="plan_memory_updated",
        content="Fifth update.", payload={}, created_at=later,
    ))
    db_session.flush()
    assert plan_intelligence._integrity_audit_due(db_session, task) is True
