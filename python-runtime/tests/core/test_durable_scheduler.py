from concurrent.futures import ThreadPoolExecutor

import pytest

from app.core.durable_scheduler import (
    SQLiteTaskPlanStore,
    TaskPlanAlreadyExists,
    TaskPlanNotFound,
)
from app.core.scheduler import ScheduledTask, TaskPlan, TaskStatus


def plan_with_dependency():
    return TaskPlan(tasks={
        "write": ScheduledTask(task_id="write", agent_id="writer", instruction="Write draft", max_attempts=2),
        "review": ScheduledTask(task_id="review", agent_id="reviewer", instruction="Review draft", dependencies=["write"]),
    })


def test_task_plan_survives_store_reopen_and_dependency_progression(tmp_path):
    path = tmp_path / "workflow.sqlite3"
    store = SQLiteTaskPlanStore(path)
    store.create("plan-1", plan_with_dependency())
    assert store.refresh_ready("plan-1") == ["write"]

    claimed = store.claim_ready("plan-1", 1)
    assert [task.task_id for task in claimed] == ["write"]
    assert store.get("plan-1").tasks["write"].status == TaskStatus.RUNNING

    reopened = SQLiteTaskPlanStore(path)
    assert reopened.get("plan-1").tasks["write"].attempt == 1
    assert reopened.complete("plan-1", "write", result_ref="artifact:123") == ["review"]
    assert reopened.get("plan-1").tasks["review"].status == TaskStatus.READY


def test_duplicate_plan_and_unknown_plan_are_explicit(tmp_path):
    store = SQLiteTaskPlanStore(tmp_path / "workflow.sqlite3")
    store.create("plan-1", plan_with_dependency())
    with pytest.raises(TaskPlanAlreadyExists):
        store.create("plan-1", plan_with_dependency())
    with pytest.raises(TaskPlanNotFound):
        store.get("missing")


def test_retry_limits_and_interrupted_task_recovery_are_explicit(tmp_path):
    store = SQLiteTaskPlanStore(tmp_path / "workflow.sqlite3")
    plan = TaskPlan(tasks={
        "task": ScheduledTask(task_id="task", agent_id="agent", instruction="Process", max_attempts=2)
    })
    store.create("plan", plan)
    store.refresh_ready("plan")
    store.claim_ready("plan", 1)
    store.fail("plan", "task", "Temporary issue", retryable=True)
    assert store.get("plan").tasks["task"].status == TaskStatus.READY
    store.claim_ready("plan", 1)
    recovered = store.recover_interrupted("plan", retry_running=True)
    assert recovered.tasks["task"].status == TaskStatus.FAILED
    assert "uncertain" in recovered.tasks["task"].error


def test_interrupted_task_is_not_replayed_by_default(tmp_path):
    store = SQLiteTaskPlanStore(tmp_path / "workflow.sqlite3")
    store.create("plan", TaskPlan(tasks={
        "task": ScheduledTask(task_id="task", agent_id="agent", instruction="Send message", max_attempts=3)
    }))
    store.refresh_ready("plan")
    store.claim_ready("plan", 1)
    recovered = store.recover_interrupted("plan")
    assert recovered.tasks["task"].status == TaskStatus.FAILED
    assert "not automatically replayed" in recovered.tasks["task"].error


def test_concurrent_claims_do_not_claim_the_same_task(tmp_path):
    store = SQLiteTaskPlanStore(tmp_path / "workflow.sqlite3")
    store.create("plan", TaskPlan(tasks={
        f"task-{i}": ScheduledTask(task_id=f"task-{i}", agent_id="agent", instruction="Work")
        for i in range(8)
    }))
    store.refresh_ready("plan")

    def claim():
        return [task.task_id for task in store.claim_ready("plan", 4)]

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(lambda _: claim(), range(2)))
    assert len(first) + len(second) == 8
    assert set(first).isdisjoint(second)
    assert all(task.status == TaskStatus.RUNNING for task in store.get("plan").tasks.values())
