from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import select

from app import models
from app.contracts.run import RunOptions, RunRequest
from app.db import SessionLocal
from app.services.executions import manager

router = APIRouter(prefix="/v2/executions", tags=["executions-v2"])


class CreateExecutionRequest(BaseModel):
    project_id: str
    root_agent_id: str
    task: str
    history: list[dict] = Field(default_factory=list)
    options: RunOptions = Field(default_factory=RunOptions)


def _execution_detail(row: models.Execution) -> dict:
    return {
        "id": row.id,
        "status": row.status,
        "final_output": row.final_output,
        "totals": row.totals or {},
        "error": row.error,
        "started_at": row.started_at,
        "ended_at": row.ended_at,
    }


@router.post("")
async def create_execution(payload: CreateExecutionRequest):
    execution_id = str(uuid4())
    try:
        req = RunRequest(
            execution_id=execution_id,
            project_id=payload.project_id,
            root_agent_id=payload.root_agent_id,
            task=payload.task,
            history=payload.history,
            options=payload.options,
        )
        return manager.start(req)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("")
def list_executions(
    project_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    db = SessionLocal()
    try:
        query = select(models.Execution).order_by(models.Execution.started_at.desc()).limit(limit)
        if project_id:
            query = query.where(models.Execution.project_id == project_id)
        rows = db.execute(query).scalars().all()
        return [
            {
                "id": row.id,
                "task_preview": row.input_task[:200],
                "status": row.status,
                "started_at": row.started_at,
                "ended_at": row.ended_at,
                "totals": row.totals or {},
            }
            for row in rows
        ]
    finally:
        db.close()


@router.get("/{execution_id}")
def get_execution(execution_id: str):
    db = SessionLocal()
    try:
        row = db.get(models.Execution, execution_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Execution not found")
        return _execution_detail(row)
    finally:
        db.close()


@router.get("/{execution_id}/events")
def get_events(execution_id: str, after_seq: int = Query(default=0, ge=0)):
    db = SessionLocal()
    try:
        if db.get(models.Execution, execution_id) is None:
            raise HTTPException(status_code=404, detail="Execution not found")
        rows = db.execute(
            select(models.ExecutionEventRow)
            .where(
                models.ExecutionEventRow.execution_id == execution_id,
                models.ExecutionEventRow.seq > after_seq,
            )
            .order_by(models.ExecutionEventRow.seq)
        ).scalars().all()
        return [
            {
                "execution_id": row.execution_id,
                "seq": row.seq,
                "ts": row.timestamp,
                "type": row.type,
                "span_id": row.span_id,
                "parent_span_id": row.parent_span_id,
                "kind": row.kind,
                "name": row.name,
                "status": row.status,
                "data": row.data or {},
            }
            for row in rows
        ]
    finally:
        db.close()


@router.post("/{execution_id}/cancel")
async def cancel_execution(execution_id: str):
    db = SessionLocal()
    try:
        if db.get(models.Execution, execution_id) is None:
            raise HTTPException(status_code=404, detail="Execution not found")
    finally:
        db.close()

    if not await manager.cancel(execution_id):
        raise HTTPException(status_code=409, detail="Execution is no longer running")
    return {"status": "cancelling"}


@router.websocket("/{execution_id}/stream")
async def stream_execution(
    websocket: WebSocket,
    execution_id: str,
    after_seq: int = Query(default=0, ge=0),
):
    queue = await manager.hub.subscribe(execution_id)
    try:
        await websocket.accept()

        db = SessionLocal()
        try:
            rows = db.execute(
                select(models.ExecutionEventRow)
                .where(
                    models.ExecutionEventRow.execution_id == execution_id,
                    models.ExecutionEventRow.seq > after_seq,
                )
                .order_by(models.ExecutionEventRow.seq)
            ).scalars().all()
        finally:
            db.close()

        last_seq = after_seq
        for row in rows:
            await websocket.send_json({
                "execution_id": row.execution_id,
                "seq": row.seq,
                "ts": row.timestamp.isoformat(),
                "type": row.type,
                "span_id": row.span_id,
                "parent_span_id": row.parent_span_id,
                "kind": row.kind,
                "name": row.name,
                "status": row.status,
                "data": row.data or {},
            })
            last_seq = max(last_seq, row.seq)

        while True:
            event = await queue.get()
            if event.seq <= last_seq:
                continue
            await websocket.send_json(event.model_dump(mode="json"))
            last_seq = event.seq
    except WebSocketDisconnect:
        pass
    finally:
        await manager.hub.unsubscribe(execution_id, queue)
