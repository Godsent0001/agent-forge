from __future__ import annotations

import shutil
from typing import Literal
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.contracts.run import RunOptions, RunRequest
from app.core.artifact_store import ArtifactStoreError, SQLiteArtifactStore
from app.db import SessionLocal
from app.deps import get_db
from app.infra.approvals import resolve_approval
from app.infra.attachment_storage import (
    MAX_RUN_ATTACHMENT_BYTES,
    MAX_RUN_ATTACHMENTS,
    AttachmentStorageError,
    copy_clean_attachment_to_workspace,
)
from app.infra.file_security import file_response_headers
from app.infra.paths import project_dir
from app.infra.workspace import RunWorkspace
from app.services.executions import manager
from app.tools.base import ToolExecutionError

router = APIRouter(prefix="/v2/executions", tags=["executions-v2"])


class CreateExecutionRequest(BaseModel):
    project_id: str
    root_agent_id: str
    task: str
    history: list[dict] = Field(default_factory=list)
    options: RunOptions = Field(default_factory=RunOptions)
    attachment_ids: list[str] = Field(default_factory=list, max_length=MAX_RUN_ATTACHMENTS)


class ResolveApprovalRequest(BaseModel):
    decision: Literal["allow_once", "allow_run", "deny"]


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
async def create_execution(payload: CreateExecutionRequest, db: Session = Depends(get_db)):
    execution_id = str(uuid4())
    workspace: RunWorkspace | None = None
    try:
        attachment_refs = []
        if payload.attachment_ids:
            if len(set(payload.attachment_ids)) != len(payload.attachment_ids):
                raise HTTPException(status_code=422, detail="Duplicate attachment IDs are not allowed")
            project = db.get(models.Project, payload.project_id)
            if project is None:
                raise HTTPException(status_code=404, detail="Project not found")
            rows = (
                db.query(models.ProjectAttachment)
                .filter(
                    models.ProjectAttachment.project_id == payload.project_id,
                    models.ProjectAttachment.id.in_(payload.attachment_ids),
                )
                .all()
            )
            if len(rows) != len(payload.attachment_ids):
                # Unknown IDs and IDs from another project are deliberately indistinguishable.
                raise HTTPException(status_code=404, detail="Attachment not found in this project")
            if any(row.status != "clean" for row in rows):
                raise HTTPException(status_code=409, detail="Only clean, scanned attachments can be used in a run")
            if sum(row.size_bytes for row in rows) > MAX_RUN_ATTACHMENT_BYTES:
                raise HTTPException(status_code=413, detail="Run attachments exceed the 100 MiB combined limit")

            by_id = {row.id: row for row in rows}
            workspace = RunWorkspace(execution_id)
            for attachment_id in payload.attachment_ids:
                row = by_id[attachment_id]
                try:
                    relative_path = copy_clean_attachment_to_workspace(row, workspace)
                except (AttachmentStorageError, OSError) as exc:
                    raise HTTPException(status_code=409, detail="Attachment failed integrity verification") from exc
                attachment_refs.append({
                    "path": relative_path,
                    "mime": row.detected_mime,
                    "name": row.original_name,
                })

        req = RunRequest(
            execution_id=execution_id,
            project_id=payload.project_id,
            root_agent_id=payload.root_agent_id,
            task=payload.task,
            history=payload.history,
            attachments=attachment_refs,
            options=payload.options,
        )
        return manager.start(req)
    except HTTPException:
        if workspace is not None:
            shutil.rmtree(workspace.root, ignore_errors=True)
        raise
    except ValueError as exc:
        if workspace is not None:
            shutil.rmtree(workspace.root, ignore_errors=True)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception:
        if workspace is not None:
            shutil.rmtree(workspace.root, ignore_errors=True)
        raise


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

@router.post("/{execution_id}/approvals/{approval_id}")
async def resolve_execution_approval(execution_id: str, approval_id: str, payload: ResolveApprovalRequest):
    db = SessionLocal()
    try:
        if db.get(models.Execution, execution_id) is None:
            raise HTTPException(status_code=404, detail="Execution not found")
    finally:
        db.close()

    try:
        resolved = resolve_approval(execution_id=execution_id, approval_id=approval_id, decision=payload.decision)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not resolved:
        raise HTTPException(status_code=404, detail="Approval request not found or already resolved")
    return {"status": "resolved", "decision": payload.decision}


@router.get("/{execution_id}/artifacts")
def list_execution_artifacts(execution_id: str):
    db = SessionLocal()
    try:
        execution = db.get(models.Execution, execution_id)
        if execution is None:
            raise HTTPException(status_code=404, detail="Execution not found")
        project_id = execution.project_id
    finally:
        db.close()

    store = SQLiteArtifactStore(project_dir(project_id))
    return [
        record.model_dump(mode="json")
        for record in store.list_project(project_id, limit=200)
        if record.metadata.get("execution_id") == execution_id
    ]


@router.get("/{execution_id}/artifacts/{artifact_id}")
def download_execution_artifact(
    execution_id: str,
    artifact_id: str,
    version: int | None = Query(default=None, ge=1),
):
    db = SessionLocal()
    try:
        execution = db.get(models.Execution, execution_id)
        if execution is None:
            raise HTTPException(status_code=404, detail="Execution not found")
        project_id = execution.project_id
    finally:
        db.close()

    store = SQLiteArtifactStore(project_dir(project_id))
    record = store.get(artifact_id)
    if (
        record is None
        or record.project_id != project_id
        or record.metadata.get("execution_id") != execution_id
    ):
        # Do not disclose artifacts belonging to another project or execution.
        raise HTTPException(status_code=404, detail="Artifact not found")
    try:
        opened = store.open_verified(artifact_id, version)
    except ArtifactStoreError as exc:
        raise HTTPException(status_code=409, detail="Artifact failed its integrity check") from exc
    if opened is None:
        raise HTTPException(status_code=404, detail="Artifact version not found")
    _, blob_path = opened

    filename = (
        record.name.replace("\\", "_")
        .replace("/", "_")
        .replace('"', "")
        .replace("\r", "")
        .replace("\n", "")[:200]
    )
    stored_media_type = record.media_type.split(";", 1)[0].strip().lower()
    inline_media_types = {
        "image/png", "image/jpeg", "image/gif", "image/webp",
        "video/mp4", "video/webm",
        "audio/mpeg", "audio/wav", "audio/x-wav", "audio/ogg",
        "text/plain",
    }
    allow_inline = stored_media_type in inline_media_types
    # FileResponse streams from disk and honours Range requests, so large clips can seek.
    return FileResponse(
        path=blob_path,
        media_type=stored_media_type if allow_inline else "application/octet-stream",
        headers={
            "Content-Disposition": f'{"inline" if allow_inline else "attachment"}; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


@router.get("/{execution_id}/files/{relpath:path}")
def get_execution_file(execution_id: str, relpath: str):
    db = SessionLocal()
    try:
        if db.get(models.Execution, execution_id) is None:
            raise HTTPException(status_code=404, detail="Execution not found")
    finally:
        db.close()

    try:
        workspace = RunWorkspace(execution_id)
        path = workspace.resolve(relpath)
    except (ToolExecutionError, ValueError, OSError) as exc:
        raise HTTPException(status_code=404, detail="Workspace file not found") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Workspace file not found")
    return FileResponse(path=path, headers=file_response_headers(path))

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
