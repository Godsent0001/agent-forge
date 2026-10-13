from __future__ import annotations

import asyncio
import json
import math
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import update

from app import models
from app.contracts.events import EventDraft, RunEvent
from app.contracts.run import BudgetSpec, RunRequest, RunResult, Totals
from app.db import SessionLocal
from app.infra.approvals import ApprovalGateImpl
from app.services.core_adapters import Workspace
from app.services.graph_loader import load_agent_graph
from app.services.memory_store import SqlLessonStore, SqlMemoryStore
from app.services.runner_factory import get_runner
from app.tools.registry import DefaultToolFactory


def _truncate_value(value):
    if isinstance(value, str):
        if len(value) <= 2000:
            return value
        return value[:2000] + f"…[+{len(value) - 2000} chars]"
    if isinstance(value, dict):
        return {str(k): _truncate_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_truncate_value(v) for v in value]
    return value


def _bounded_data(data: dict) -> dict:
    value = _truncate_value(data or {})
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) <= 8192:
        return value
    return {"truncated": True, "preview": encoded[:7800] + "…"}

 
def _apply_project_defaults(req: RunRequest, settings: dict, parallel_execution: bool) -> RunRequest:
    """Apply validated project budget defaults and persisted parallel-tools flag."""
    raw_budget = settings.get("budget", {})
    if not isinstance(raw_budget, dict):
        raw_budget = {}
    values = req.options.budget.model_dump()
    max_calls = raw_budget.get("max_llm_calls")
    if isinstance(max_calls, int) and not isinstance(max_calls, bool) and 1 <= max_calls <= 10_000:
        values["max_llm_calls"] = max_calls
    max_seconds = raw_budget.get("max_seconds")
    if isinstance(max_seconds, int) and not isinstance(max_seconds, bool) and 1 <= max_seconds <= 86_400:
        values["max_seconds"] = max_seconds
    max_cost = raw_budget.get("max_cost_usd", values["max_cost_usd"])
    if max_cost is None:
        values["max_cost_usd"] = None
    elif isinstance(max_cost, (int, float)) and not isinstance(max_cost, bool) and math.isfinite(max_cost) and 0 <= max_cost <= 1_000_000:
        values["max_cost_usd"] = float(max_cost)
    budget = BudgetSpec.model_validate(values)
    options = req.options.model_copy(update={
        "budget": budget,
        "parallel_tools": parallel_execution is True,
    })
    return req.model_copy(update={"options": options})


class CancelTokenImpl:
    def __init__(self) -> None:
        self._cancelled = False

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        self._cancelled = True

    def raise_if_cancelled(self) -> None:
        if self._cancelled:
            raise asyncio.CancelledError


class Hub:
    def __init__(self) -> None:
        self._queues: dict[str, set[asyncio.Queue[RunEvent]]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, execution_id: str) -> asyncio.Queue[RunEvent]:
        queue: asyncio.Queue[RunEvent] = asyncio.Queue()
        async with self._lock:
            self._queues.setdefault(execution_id, set()).add(queue)
        return queue

    async def unsubscribe(self, execution_id: str, queue: asyncio.Queue[RunEvent]) -> None:
        async with self._lock:
            queues = self._queues.get(execution_id)
            if not queues:
                return
            queues.discard(queue)
            if not queues:
                self._queues.pop(execution_id, None)

    async def publish(self, event: RunEvent) -> None:
        async with self._lock:
            queues = list(self._queues.get(event.execution_id, set()))
        for queue in queues:
            await queue.put(event)


class Emitter:
    def __init__(self, execution_id: str, hub: Hub, start_seq: int = 0) -> None:
        self.execution_id = execution_id
        self.hub = hub
        self._seq = start_seq
        self._lock = asyncio.Lock()

    async def emit(self, draft: EventDraft) -> RunEvent:
        async with self._lock:
            self._seq += 1
            event = RunEvent(
                execution_id=self.execution_id,
                seq=self._seq,
                ts=datetime.now(timezone.utc),
                type=draft.type,
                span_id=draft.span_id,
                parent_span_id=draft.parent_span_id,
                kind=draft.kind,
                name=draft.name,
                status=draft.status,
                data=_bounded_data(draft.data),
            )
            await asyncio.to_thread(self._persist, event)
            await self.hub.publish(event)
            return event

    def _persist(self, event: RunEvent) -> None:
        db = SessionLocal()
        try:
            db.add(models.ExecutionEventRow(
                id=str(uuid4()),
                execution_id=event.execution_id,
                seq=event.seq,
                span_id=event.span_id,
                parent_span_id=event.parent_span_id,
                kind=event.kind,
                name=event.name,
                status=event.status,
                type=event.type,
                data=event.data,
                timestamp=event.ts,
            ))
            db.commit()
        finally:
            db.close()


class ExecutionManager:
    def __init__(self, hub: Hub | None = None) -> None:
        self.hub = hub or Hub()
        self.active: dict[str, asyncio.Task[None]] = {}
        self.tokens: dict[str, CancelTokenImpl] = {}

    def start(self, req: RunRequest) -> dict:
        db = SessionLocal()
        try:
            project = db.get(models.Project, req.project_id)
            if project is None:
                raise ValueError("Project not found")
            project_settings = dict(project.settings or {})
            project_settings["parallel_tools"] = project.parallel_execution is True
            req = _apply_project_defaults(req, project_settings, project.parallel_execution)
            graph = load_agent_graph(db, req.project_id, req.root_agent_id)
            execution = models.Execution(
                id=req.execution_id,
                project_id=req.project_id,
                root_agent_id=req.root_agent_id,
                input_task=req.task,
                status="running",
                agent_graph_snapshot=graph.model_dump(mode="json"),
            )
            db.add(execution)
            db.commit()
        finally:
            db.close()

        token = CancelTokenImpl()
        self.tokens[req.execution_id] = token
        self.active[req.execution_id] = asyncio.create_task(self._run(req, token, project_settings))
        return {"id": req.execution_id, "status": "running"}

    async def _run(self, req: RunRequest, token: CancelTokenImpl, project_settings: dict | None = None) -> None:
        emitter = Emitter(req.execution_id, self.hub)
        status = "error"
        final_output = ""
        error: str | None = None
        totals = Totals()
        try:
            db = SessionLocal()
            try:
                graph = load_agent_graph(db, req.project_id, req.root_agent_id)
            finally:
                db.close()

            await emitter.emit(EventDraft(
                type="execution_started",
                data={"root_agent_id": req.root_agent_id, "task_preview": req.task[:500]},
            ))
            runner = get_runner()
            workspace = Workspace(req.execution_id)
            approvals = ApprovalGateImpl(
                execution_id=req.execution_id,
                settings=project_settings or {},
                emit=emitter.emit,
                tool_kinds={binding.name: binding.kind for agent in graph.agents.values() for binding in agent.tools},
            )
            try:
                if runner.__class__.__name__ == "RunnerCore":
                    result: RunResult = await runner.run(
                        req,
                        graph=graph,
                        emit=emitter.emit,
                        cancel=token,
                        approvals=approvals,
                        workspace=workspace,
                        tools=DefaultToolFactory(),
                        memory=SqlMemoryStore(),
                        lessons=SqlLessonStore(),
                        intents=None,
                        run_history=None,
                    )
                else:
                    result = await runner.run(
                        req,
                        graph=graph,
                        emit=emitter.emit,
                        cancel=token,
                        approvals=approvals,
                        memory=_NoopMemory(),
                        workspace=workspace,
                        tools=_NoopTools(),
                    )
            finally:
                workspace.cleanup()

            status = result.status
            final_output = result.final_output
            error = result.error
            totals = result.totals
        except asyncio.CancelledError:
            token.cancel()
            status = "cancelled"
            error = "Execution cancelled"
        except Exception as exc:
            status = "error"
            error = str(exc)
        finally:
            db = SessionLocal()
            try:
                execution = db.get(models.Execution, req.execution_id)
                if execution is not None:
                    execution.status = status
                    execution.final_output = final_output
                    execution.error = error
                    execution.totals = totals.model_dump()
                    execution.ended_at = datetime.now(timezone.utc)
                    execution.completed_at = execution.ended_at
                    db.commit()
            finally:
                db.close()

            await emitter.emit(EventDraft(
                type="execution_ended",
                data={
                    "status": status,
                    "final_output": final_output,
                    "totals": totals.model_dump(),
                    "error": error,
                },
            ))
            self.active.pop(req.execution_id, None)
            self.tokens.pop(req.execution_id, None)

    async def cancel(self, execution_id: str) -> bool:
        token = self.tokens.get(execution_id)
        task = self.active.get(execution_id)
        if not token or not task:
            return False
        token.cancel()
        task.cancel()
        return True

    def mark_running_interrupted(self) -> int:
        db = SessionLocal()
        try:
            result = db.execute(
                update(models.Execution)
                .where(models.Execution.status == "running")
                .values(status="interrupted", ended_at=datetime.now(timezone.utc))
            )
            db.commit()
            return result.rowcount or 0
        finally:
            db.close()

    async def shutdown(self) -> None:
        tasks = list(self.active.values())
        for token in self.tokens.values():
            token.cancel()
        for task in tasks:
            task.cancel()
        if tasks:
            done, pending = await asyncio.wait(tasks, timeout=3.0)
            if pending:
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
            if done:
                await asyncio.gather(*done, return_exceptions=True)


class _NoopApprovals:
    async def check(self, **kwargs) -> bool:
        return True


class _NoopMemory:
    async def recall(self, *args, **kwargs):
        return []

    async def add(self, *args, **kwargs):
        return None

    async def summary(self, *args, **kwargs):
        return ""

    async def set_summary(self, *args, **kwargs):
        return None


class _NoopWorkspace:
    root = None

    def resolve(self, rel):
        raise RuntimeError("FakeRunner does not use a workspace")

    def new_path(self, name):
        raise RuntimeError("FakeRunner does not use a workspace")

    def relative(self, p):
        raise RuntimeError("FakeRunner does not use a workspace")


class _NoopTools:
    def build(self, binding):
        raise RuntimeError("FakeRunner does not use tools")


manager = ExecutionManager()
