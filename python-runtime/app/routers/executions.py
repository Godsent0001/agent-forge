from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import models, schemas
from app.contracts.run import RunRequest as CoreRunRequest
from app.db import SessionLocal
from app.deps import get_db
from app.services.executions import manager as core_execution_manager
from app.ws import manager as legacy_ws_manager

router = APIRouter(prefix="/executions", tags=["executions"])


@router.websocket("/{execution_id}/stream")
async def stream_execution(websocket: WebSocket, execution_id: str):
    await legacy_ws_manager.connect(execution_id, websocket)
    try:
        while True:
            # Server-push only; receive_text is used to detect client disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        legacy_ws_manager.disconnect(execution_id, websocket)


class RunRequest(BaseModel):
    project_id: str
    root_agent_id: str
    task: str


@router.post("", response_model=schemas.ExecutionOut)
async def run_execution(
    payload: RunRequest,
    db: Session = Depends(get_db),
):
    """Legacy-compatible API boundary backed by the single RunnerCore engine.

    Keep the established request/response schema, but delegate creation, graph
    validation, persistence, approvals, event sequencing, cancellation, and
    execution to the same manager used by /v2/executions.
    """
    execution_id = str(uuid4())
    request = CoreRunRequest(
        execution_id=execution_id,
        project_id=payload.project_id,
        root_agent_id=payload.root_agent_id,
        task=payload.task,
    )
    try:
        core_execution_manager.start(request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    execution = db.get(models.Execution, execution_id)
    if execution is None:
        # The manager commits the execution before scheduling the run. Treat a
        # missing row as an internal consistency failure rather than fabricate
        # a response that the frontend cannot subsequently retrieve.
        raise HTTPException(status_code=500, detail="Execution was not persisted")
    return execution


@router.get("/{execution_id}", response_model=schemas.ExecutionOut)
def get_execution(execution_id: str, db: Session = Depends(get_db)):
    execution = db.get(models.Execution, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return execution


@router.get("/{execution_id}/events", response_model=list[schemas.ExecutionEventOut])
def get_execution_events(execution_id: str, db: Session = Depends(get_db)):
    if db.get(models.Execution, execution_id) is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    return (
        db.query(models.ExecutionEventRow)
        .filter(models.ExecutionEventRow.execution_id == execution_id)
        .order_by(models.ExecutionEventRow.timestamp)
        .all()
    )
