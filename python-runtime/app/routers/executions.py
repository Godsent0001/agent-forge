from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import models, schemas
from app.deps import get_db
from app.runtime.engine import ExecutionEngine
from app.ws import manager

router = APIRouter(prefix="/executions", tags=["executions"])


@router.websocket("/{execution_id}/stream")
async def stream_execution(websocket: WebSocket, execution_id: str):
    await manager.connect(execution_id, websocket)
    try:
        while True:
            # This socket is server-push only; we just need to detect disconnect.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(execution_id, websocket)


class RunRequest(BaseModel):
    project_id: str
    root_agent_id: str
    task: str


@router.post("", response_model=schemas.ExecutionOut)
async def run_execution(payload: RunRequest, db: Session = Depends(get_db)):
    engine = ExecutionEngine(db)
    execution = await engine.run(payload.project_id, payload.root_agent_id, payload.task)
    return execution


@router.get("/{execution_id}", response_model=schemas.ExecutionOut)
def get_execution(execution_id: str, db: Session = Depends(get_db)):
    execution = db.get(models.Execution, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return execution


@router.get("/{execution_id}/events", response_model=list[schemas.ExecutionEventOut])
def get_execution_events(execution_id: str, db: Session = Depends(get_db)):
    return (
        db.query(models.ExecutionEventRow)
        .filter(models.ExecutionEventRow.execution_id == execution_id)
        .order_by(models.ExecutionEventRow.timestamp)
        .all()
    )
