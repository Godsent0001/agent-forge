from __future__ import annotations

import json

from sqlalchemy.orm import sessionmaker

from app import models
from app.services import task_memory


def _conversation(db_session):
    project = models.Project(name="Task memory tests")
    db_session.add(project)
    db_session.flush()
    agent = models.Agent(project_id=project.id, name="Memory agent", provider="fake", model="fake/demo")
    db_session.add(agent)
    db_session.flush()
    conversation = models.Conversation(project_id=project.id, agent_id=agent.id)
    db_session.add(conversation)
    db_session.commit()
    return project, agent, conversation


def test_follow_up_preserves_original_objective_and_writes_compact_projection(
    db_session, monkeypatch, tmp_path
):
    _, _, conversation = _conversation(db_session)
    monkeypatch.setattr(task_memory, "project_dir", lambda _project_id: tmp_path)

    db_session.add(models.ConversationMessage(
        conversation_id=conversation.id,
        role="user",
        content="Build a production-grade payment reconciliation engine.",
    ))
    db_session.commit()
    task_id, first_context = task_memory.prepare_task_state(
        db_session, conversation, "Start by designing the settlement schema."
    )
    assert task_id
    assert "Original objective:" in first_context
    assert "payment reconciliation engine" in first_context

    same_task_id, follow_up_context = task_memory.prepare_task_state(
        db_session, conversation, "Now implement transaction matching and retries."
    )
    assert same_task_id == task_id

    state = db_session.get(models.TaskState, task_id)
    assert state is not None
    assert state.original_objective == "Build a production-grade payment reconciliation engine."
    assert state.current_instruction == "Now implement transaction matching and retries."
    assert state.version == 2
    assert db_session.query(models.TaskStateEvent).filter_by(task_state_id=task_id).count() == 3
    assert "Build a production-grade payment reconciliation engine." in follow_up_context

    state_file = tmp_path / "workspace" / ".agentforge" / "memory" / "tasks" / task_id / "STATE.md"
    registry_file = tmp_path / "workspace" / ".agentforge" / "memory" / "registry.json"
    assert state_file.is_file()
    assert "Original objective" in state_file.read_text(encoding="utf-8")
    registry = json.loads(registry_file.read_text(encoding="utf-8"))
    assert registry["active_tasks_by_conversation"][conversation.id] == task_id


def test_explicit_task_switch_pauses_previous_task(db_session, monkeypatch, tmp_path):
    _, _, conversation = _conversation(db_session)
    monkeypatch.setattr(task_memory, "project_dir", lambda _project_id: tmp_path)

    first_id, _ = task_memory.prepare_task_state(db_session, conversation, "Build the payment engine.")
    second_id, context = task_memory.prepare_task_state(
        db_session, conversation, "New task: Research Nigerian payment providers."
    )

    assert second_id != first_id
    assert db_session.get(models.TaskState, first_id).status == "paused"
    assert db_session.query(models.TaskStateEvent).filter_by(task_state_id=first_id, event_type="task_paused").count() == 1
    second = db_session.get(models.TaskState, second_id)
    assert second.status == "active"
    assert second.original_objective == "New task: Research Nigerian payment providers."
    assert "Research Nigerian payment providers" in context


def test_execution_result_is_recorded_without_llm(db_session, monkeypatch, tmp_path):
    project, agent, conversation = _conversation(db_session)
    monkeypatch.setattr(task_memory, "project_dir", lambda _project_id: tmp_path)
    task_id, _ = task_memory.prepare_task_state(db_session, conversation, "Build the reconciliation engine.")

    execution = models.Execution(
        id="task-memory-execution",
        project_id=project.id,
        root_agent_id=agent.id,
        input_task="Build the reconciliation engine.",
        status="completed",
        final_output="Created the initial reconciliation pipeline.",
    )
    db_session.add(execution)
    db_session.commit()

    monkeypatch.setattr(
        "app.db.SessionLocal",
        sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False),
    )
    task_memory.record_task_execution_result(
        task_id,
        execution.id,
        "completed",
        "Created the initial reconciliation pipeline.",
        None,
    )

    db_session.expire_all()
    state = db_session.get(models.TaskState, task_id)
    assert state.state_json["last_execution"]["status"] == "completed"
    assert len(state.state_json["recent_executions"]) == 1
    assert "initial reconciliation pipeline" in state.state_json["last_execution"]["summary"]
    event = (
        db_session.query(models.TaskStateEvent)
        .filter_by(task_state_id=task_id, event_type="execution_result")
        .one()
    )
    assert event.source_execution_id == execution.id


def test_agent_authored_updates_are_structured_bounded_and_versioned(
    db_session, monkeypatch, tmp_path
):
    project, agent, conversation = _conversation(db_session)
    monkeypatch.setattr(task_memory, "project_dir", lambda _project_id: tmp_path)
    task_id, _ = task_memory.prepare_task_state(db_session, conversation, "Build the reconciliation engine.")
    task_row = db_session.get(models.TaskState, task_id)
    task_row.state_json = {
        **task_row.state_json,
        "plan": {
            "nodes": [{
                "id": "schema-node",
                "parent_id": task_id,
                "type": "task",
                "title": "Database schema created",
                "status": "active",
                "source": "agent",
                "version": 1,
            }]
        },
    }
    db_session.commit()
    execution = models.Execution(
        id="task-memory-update-execution",
        project_id=project.id,
        root_agent_id=agent.id,
        input_task="Build the reconciliation engine.",
        status="running",
    )
    db_session.add(execution)
    db_session.commit()
    monkeypatch.setattr(
        "app.db.SessionLocal",
        sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False),
    )

    task_memory.bind_task_state_to_execution(task_id, execution.id)
    result = task_memory.apply_task_state_update(
        task_id,
        execution.id,
        {
            "constraints_add": ["Use PostgreSQL", "Maintain an auditable ledger"],
            "decisions_add": ["Use idempotency keys"],
            "completed_add": ["Database schema created"],
            "remaining": ["Implement transaction matching"],
            "blockers": [],
            "next_action": "Implement transaction matching",
            "note": "Database design milestone verified.",
        },
    )

    db_session.expire_all()
    state = db_session.get(models.TaskState, task_id)
    assert result["updated"] is True
    assert state.version == 2
    assert state.state_json["constraints"] == ["Use PostgreSQL", "Maintain an auditable ledger"]
    assert state.state_json["decisions"] == ["Use idempotency keys"]
    assert state.state_json["completed"] == ["Database schema created"]
    assert state.state_json["plan"]["nodes"][0]["status"] == "completed"
    assert state.state_json["plan"]["nodes"][0]["verified_by_execution_id"] == execution.id
    assert state.state_json["remaining"] == ["Implement transaction matching"]
    assert state.state_json["blockers"] == []
    assert state.state_json["next_action"] == "Implement transaction matching"
    event = (
        db_session.query(models.TaskStateEvent)
        .filter_by(task_state_id=task_id, event_type="agent_state_update")
        .one()
    )
    assert event.source_execution_id == execution.id
    task_header = task_memory._render_context(db_session, state)
    assert "Use PostgreSQL" in task_header
    assert "Implement transaction matching" in task_header
    assert len(task_header) <= task_memory._MAX_HEADER_CHARS
    state_file = tmp_path / "workspace" / ".agentforge" / "memory" / "tasks" / task_id / "STATE.md"
    assert "Use PostgreSQL" in state_file.read_text(encoding="utf-8")


def test_live_instruction_updates_active_task_without_resetting_objective(
    db_session, monkeypatch, tmp_path
):
    project, agent, conversation = _conversation(db_session)
    monkeypatch.setattr(task_memory, "project_dir", lambda _project_id: tmp_path)
    task_id, _ = task_memory.prepare_task_state(db_session, conversation, "Build the reconciliation engine.")
    execution = models.Execution(
        id="task-memory-live-execution",
        project_id=project.id,
        root_agent_id=agent.id,
        input_task="Build the reconciliation engine.",
        status="running",
    )
    db_session.add(execution)
    db_session.commit()
    monkeypatch.setattr(
        "app.db.SessionLocal",
        sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False),
    )

    task_memory.record_live_task_instruction(
        conversation.id,
        execution.id,
        "Also add duplicate transaction detection.",
    )

    db_session.expire_all()
    state = db_session.get(models.TaskState, task_id)
    assert state.original_objective == "Build the reconciliation engine."
    assert state.current_instruction == "Also add duplicate transaction detection."
    event = (
        db_session.query(models.TaskStateEvent)
        .filter_by(task_state_id=task_id, event_type="live_user_instruction")
        .one()
    )
    assert event.source_execution_id == execution.id


def test_greeting_is_not_mistaken_for_the_task_objective(db_session, monkeypatch, tmp_path):
    _, _, conversation = _conversation(db_session)
    monkeypatch.setattr(task_memory, "project_dir", lambda _project_id: tmp_path)
    db_session.add(models.ConversationMessage(
        conversation_id=conversation.id,
        role="user",
        content="Hello",
    ))
    db_session.commit()

    task_id, _ = task_memory.prepare_task_state(
        db_session, conversation, "Build a Nigerian settlement reconciliation engine."
    )

    state = db_session.get(models.TaskState, task_id)
    assert state.original_objective == "Build a Nigerian settlement reconciliation engine."


def test_live_instruction_targets_the_execution_task_after_a_task_switch(
    db_session, monkeypatch, tmp_path
):
    project, agent, conversation = _conversation(db_session)
    monkeypatch.setattr(task_memory, "project_dir", lambda _project_id: tmp_path)
    first_id, _ = task_memory.prepare_task_state(db_session, conversation, "Build the payment engine.")
    execution = models.Execution(
        id="task-memory-bound-execution",
        project_id=project.id,
        root_agent_id=agent.id,
        input_task="Build the payment engine.",
        status="running",
    )
    db_session.add(execution)
    db_session.commit()
    monkeypatch.setattr(
        "app.db.SessionLocal",
        sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False),
    )
    task_memory.bind_task_state_to_execution(first_id, execution.id)

    second_id, _ = task_memory.prepare_task_state(
        db_session, conversation, "New task: Research settlement providers."
    )
    assert db_session.get(models.TaskState, first_id).status == "paused"

    task_memory.record_live_task_instruction(
        conversation.id, execution.id, "Stop the payment-engine build after the current safe checkpoint."
    )

    db_session.expire_all()
    first = db_session.get(models.TaskState, first_id)
    second = db_session.get(models.TaskState, second_id)
    assert first.current_instruction.startswith("Stop the payment-engine build")
    assert first.status == "paused"
    assert second.current_instruction == "New task: Research settlement providers."
    assert second.status == "active"


def test_paused_task_can_be_resumed_by_id_without_losing_its_state(
    db_session, monkeypatch, tmp_path
):
    _, _, conversation = _conversation(db_session)
    monkeypatch.setattr(task_memory, "project_dir", lambda _project_id: tmp_path)
    first_id, _ = task_memory.prepare_task_state(
        db_session, conversation, "Build the payment reconciliation engine."
    )
    second_id, _ = task_memory.prepare_task_state(
        db_session, conversation, "New task: Research settlement providers."
    )
    resumed_id, context = task_memory.prepare_task_state(
        db_session, conversation, f"Resume task: {first_id[:8]}"
    )

    first = db_session.get(models.TaskState, first_id)
    second = db_session.get(models.TaskState, second_id)
    assert resumed_id == first_id
    assert first.status == "active"
    assert second.status == "paused"
    assert first.original_objective == "Build the payment reconciliation engine."
    assert "Build the payment reconciliation engine." in context
    assert db_session.query(models.TaskStateEvent).filter_by(
        task_state_id=first_id, event_type="task_resumed"
    ).count() == 1


def test_unknown_resume_id_does_not_overwrite_the_active_task(db_session, monkeypatch, tmp_path):
    _, _, conversation = _conversation(db_session)
    monkeypatch.setattr(task_memory, "project_dir", lambda _project_id: tmp_path)
    task_id, _ = task_memory.prepare_task_state(db_session, conversation, "Build the payment engine.")

    import pytest
    with pytest.raises(ValueError, match="Could not uniquely identify"):
        task_memory.prepare_task_state(db_session, conversation, "Resume task: deadbeef")

    state = db_session.get(models.TaskState, task_id)
    assert state.status == "active"
    assert state.original_objective == "Build the payment engine."
    assert state.current_instruction == "Build the payment engine."


def test_agent_cannot_update_an_unbound_execution_task_pair(
    db_session, monkeypatch, tmp_path
):
    project, agent, conversation = _conversation(db_session)
    monkeypatch.setattr(task_memory, "project_dir", lambda _project_id: tmp_path)
    task_id, _ = task_memory.prepare_task_state(db_session, conversation, "Build the payment engine.")
    execution = models.Execution(
        id="task-memory-unbound-execution",
        project_id=project.id,
        root_agent_id=agent.id,
        input_task="Build the payment engine.",
        status="running",
    )
    db_session.add(execution)
    db_session.commit()
    monkeypatch.setattr(
        "app.db.SessionLocal",
        sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False),
    )

    import pytest
    with pytest.raises(ValueError, match="not authorized"):
        task_memory.apply_task_state_update(
            task_id, execution.id, {"decisions_add": ["Use idempotency keys"]}
        )



def test_project_task_can_be_resumed_from_a_different_conversation(db_session, monkeypatch, tmp_path):
    project, agent, first_conversation = _conversation(db_session)
    monkeypatch.setattr(task_memory, "project_dir", lambda _project_id: tmp_path)
    task_id, _ = task_memory.prepare_task_state(
        db_session, first_conversation, "Build a multi-stage AI research platform."
    )

    second_conversation = models.Conversation(
        project_id=project.id,
        agent_id=agent.id,
        title="Continue the research platform",
    )
    db_session.add(second_conversation)
    db_session.commit()

    resumed_id, context = task_memory.prepare_task_state(
        db_session,
        second_conversation,
        f"Resume task: {task_id[:8]}",
    )

    db_session.expire_all()
    resumed = db_session.get(models.TaskState, task_id)
    assert resumed_id == task_id
    assert resumed.conversation_id == second_conversation.id
    assert resumed.original_objective == "Build a multi-stage AI research platform."
    assert "multi-stage AI research platform" in context
    assert db_session.query(models.TaskState).filter_by(project_id=project.id).count() == 1
