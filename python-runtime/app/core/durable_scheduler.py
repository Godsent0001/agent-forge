"""SQLite-persisted task-plan state machine for recoverable agent workflows.

This is a reusable orchestration primitive. RunnerCore persists its task-plan
claims and transitions here; the legacy HTTP execution route remains unchanged.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from app.core.scheduler import ScheduledTask, TaskPlan, TaskStatus


class TaskPlanNotFound(KeyError):
    pass


class TaskPlanAlreadyExists(ValueError):
    pass


class SQLiteTaskPlanStore:
    """Persist task plans and make state transitions atomic across processes."""

    def __init__(self, database_path: str | Path):
        self.database_path = str(database_path)
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=15.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            with connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS task_plans ("
                    "plan_id TEXT PRIMARY KEY, schema_version INTEGER NOT NULL, "
                    "payload TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
                )

    @staticmethod
    def _timestamp() -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _load_payload(payload: str) -> TaskPlan:
        return TaskPlan.model_validate_json(payload)

    def create(self, plan_id: str, plan: TaskPlan) -> TaskPlan:
        plan_id = plan_id.strip()
        if not plan_id:
            raise ValueError("plan_id must not be blank.")
        now = self._timestamp()
        payload = plan.model_dump_json()
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            exists = connection.execute("SELECT 1 FROM task_plans WHERE plan_id=?", (plan_id,)).fetchone()
            if exists:
                connection.rollback()
                raise TaskPlanAlreadyExists(plan_id)
            connection.execute(
                "INSERT INTO task_plans(plan_id, schema_version, payload, created_at, updated_at) "
                "VALUES (?, 1, ?, ?, ?)",
                (plan_id, payload, now, now),
            )
            connection.commit()
        return self.get(plan_id)

    def get(self, plan_id: str) -> TaskPlan:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT payload FROM task_plans WHERE plan_id=?", (plan_id,)).fetchone()
        if row is None:
            raise TaskPlanNotFound(plan_id)
        return self._load_payload(row["payload"])

    def list_ids(self, *, limit: int = 100, offset: int = 0) -> list[str]:
        limit = min(500, max(1, int(limit)))
        offset = max(0, int(offset))
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT plan_id FROM task_plans ORDER BY updated_at, plan_id LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [row["plan_id"] for row in rows]

    def _mutate(self, plan_id: str, operation):
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT payload FROM task_plans WHERE plan_id=?", (plan_id,)).fetchone()
            if row is None:
                connection.rollback()
                raise TaskPlanNotFound(plan_id)
            plan = self._load_payload(row["payload"])
            result = operation(plan)
            connection.execute(
                "UPDATE task_plans SET payload=?, updated_at=? WHERE plan_id=?",
                (plan.model_dump_json(), self._timestamp(), plan_id),
            )
            connection.commit()
            return result, plan

    def refresh_ready(self, plan_id: str) -> list[str]:
        result, _ = self._mutate(plan_id, lambda plan: plan.refresh_ready())
        return result

    def claim_ready(self, plan_id: str, limit: int) -> list[ScheduledTask]:
        result, _ = self._mutate(plan_id, lambda plan: plan.claim_ready(limit))
        return result

    def complete(self, plan_id: str, task_id: str, *, result_ref: str | None = None) -> list[str]:
        result, _ = self._mutate(plan_id, lambda plan: plan.complete(task_id, result_ref=result_ref))
        return result

    def fail(self, plan_id: str, task_id: str, error: str, *, retryable: bool = False) -> list[str]:
        result, _ = self._mutate(plan_id, lambda plan: plan.fail(task_id, error, retryable=retryable))
        return result

    def cancel_pending(self, plan_id: str) -> None:
        self._mutate(plan_id, lambda plan: plan.cancel_pending())

    def recover_interrupted(self, plan_id: str, *, retry_running: bool = False) -> TaskPlan:
        """Explicitly reconcile RUNNING tasks after a process restart.

        A RUNNING task has an uncertain outcome. By default it becomes FAILED,
        which blocks dependants; callers may explicitly choose retry_running=True
        when the task's operation is known to be safe to repeat.
        """
        def reconcile(plan: TaskPlan) -> None:
            for task in plan.tasks.values():
                if task.status != TaskStatus.RUNNING:
                    continue
                if retry_running and task.attempt < task.max_attempts:
                    task.status = TaskStatus.READY
                    task.error = "Recovered after interruption; retry explicitly authorized."
                else:
                    task.status = TaskStatus.FAILED
                    task.error = "Outcome uncertain after interruption; not automatically replayed."
            plan.refresh_ready()
        _, plan = self._mutate(plan_id, reconcile)
        return plan
