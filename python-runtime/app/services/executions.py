from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, update

from app import models
from app.contracts.events import EventDraft, RunEvent
from app.contracts.run import RunRequest, RunResult, Totals
from app.contracts.runner import CancelToken
from app.db import SessionLocal
from app.services.graph_loader import load_agent_graph
from app.services.runner_factory import get_runner


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
        self.active[req.execution_id] = asyncio.create_task(self._run(req, token))
        return {"id": req.execution_id, "status": "running"}

    async def _run(self, req: RunRequest, token: CancelTokenImpl) -> None:
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
            result: RunResult = await runner.run(
                req,
                graph=graph,
                emit=emitter.emit,
                cancel=token,
                approvals=_NoopApprovals(),
                memory=_NoopMemory(),
                workspace=_NoopWorkspace(),
                tools=_NoopTools(),
            )
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
            await asyncio.gather(*tasks, return_exceptions=True)


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
