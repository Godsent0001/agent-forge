"""Deterministic dependency-aware scheduler primitives for Python core."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class TaskStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class ScheduledTask(BaseModel):
    task_id: str
    agent_id: str
    instruction: str
    dependencies: list[str] = Field(default_factory=list)
    priority: int = 0
    status: TaskStatus = TaskStatus.PENDING
    attempt: int = 0
    max_attempts: int = 1
    result_ref: str | None = None
    error: str | None = None


class TaskPlan(BaseModel):
    tasks: dict[str, ScheduledTask]
    max_tasks: int = 100

    @model_validator(mode="after")
    def validate_graph(self) -> "TaskPlan":
        if len(self.tasks) > self.max_tasks:
            raise ValueError(f"Task count exceeds limit {self.max_tasks}.")

        for key, task in self.tasks.items():
            if key != task.task_id:
                raise ValueError(f"Task key {key!r} does not match task_id.")
            missing = set(task.dependencies) - set(self.tasks)
            if missing:
                raise ValueError(
                    f"Task {key!r} has missing dependencies: {sorted(missing)}."
                )
            if key in task.dependencies:
                raise ValueError(f"Task {key!r} depends on itself.")

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str) -> None:
            if task_id in visiting:
                raise ValueError(f"Dependency cycle detected at {task_id!r}.")
            if task_id in visited:
                return
            visiting.add(task_id)
            for dependency in self.tasks[task_id].dependencies:
                visit(dependency)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in self.tasks:
            visit(task_id)
        return self

    def refresh_ready(self) -> list[str]:
        ready: list[str] = []
        for task in self.tasks.values():
            if task.status != TaskStatus.PENDING:
                continue
            states = [self.tasks[dependency].status for dependency in task.dependencies]
            if any(
                state in (TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.BLOCKED)
                for state in states
            ):
                task.status = TaskStatus.BLOCKED
                task.error = "A prerequisite did not complete successfully."
            elif all(state == TaskStatus.COMPLETED for state in states):
                task.status = TaskStatus.READY
                ready.append(task.task_id)
        return ready

    def claim_ready(self, limit: int) -> list[ScheduledTask]:
        """Claim ready tasks deterministically by priority, then task ID."""
        claimed: list[ScheduledTask] = []
        ready = sorted(
            (task for task in self.tasks.values() if task.status == TaskStatus.READY),
            key=lambda task: (-task.priority, task.task_id),
        )
        for task in ready[: max(0, limit)]:
            task.status = TaskStatus.RUNNING
            task.attempt += 1
            claimed.append(task)
        return claimed

    def complete(self, task_id: str, *, result_ref: str | None = None) -> list[str]:
        task = self._get(task_id)
        if task.status != TaskStatus.RUNNING:
            raise ValueError(
                f"Cannot complete {task_id!r} from {task.status.value}."
            )
        task.status = TaskStatus.COMPLETED
        task.result_ref = result_ref
        task.error = None
        return self.refresh_ready()

    def fail(
        self, task_id: str, error: str, *, retryable: bool = False
    ) -> list[str]:
        task = self._get(task_id)
        if task.status != TaskStatus.RUNNING:
            raise ValueError(f"Cannot fail {task_id!r} from {task.status.value}.")
        task.error = error[:1000]
        task.status = (
            TaskStatus.READY
            if retryable and task.attempt < task.max_attempts
            else TaskStatus.FAILED
        )
        return self.refresh_ready()

    def cancel_pending(self) -> None:
        for task in self.tasks.values():
            if task.status in (TaskStatus.PENDING, TaskStatus.READY):
                task.status = TaskStatus.CANCELLED

    def _get(self, task_id: str) -> ScheduledTask:
        if task_id not in self.tasks:
            raise KeyError(f"Unknown task_id {task_id!r}.")
        return self.tasks[task_id]

    @property
    def terminal(self) -> bool:
        return all(
            task.status
            in (
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
                TaskStatus.BLOCKED,
            )
            for task in self.tasks.values()
        )

    @property
    def successful(self) -> bool:
        return self.terminal and all(
            task.status == TaskStatus.COMPLETED for task in self.tasks.values()
        )
