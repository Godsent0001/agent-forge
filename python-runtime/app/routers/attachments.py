"""Project-scoped attachment routes; uploaded bytes never share the generated-file routes."""
from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app import models
from app.deps import get_db
from app.infra.attachment_storage import (
    MAX_ATTACHMENT_BYTES,
    MAX_PROJECT_UPLOAD_BYTES,
    AttachmentStorageError,
    content_disposition,
    new_storage_key,
    promote_quarantined_blob_to_clean,
    promote_staged_file,
    remove_attachment_blobs,
    resolve_blob,
    safe_original_name,
    scan_attachment,
    stream_to_staging,
    validate_attachment,
)

router = APIRouter(prefix="/v2/projects", tags=["project-attachments"])
UPLOAD_LOCK = asyncio.Lock()
_UPLOAD_HEADER_ALLOWANCE = 1024 * 1024


def attachment_out(row: models.ProjectAttachment) -> dict:
    # Deliberately omit storage_key, filesystem roots and declared MIME claims.
    return {
        "id": row.id,
        "project_id": row.project_id,
        "name": row.original_name,
        "mime": row.detected_mime,
        "size_bytes": row.size_bytes,
        "status": row.status,
        "created_at": row.created_at,
        "scanned_at": row.scanned_at,
    }


def _project_or_404(db: Session, project_id: str) -> models.Project:
    project = db.get(models.Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _lookup_attachment_or_404(
    db: Session, project_id: str, attachment_id: str
) -> models.ProjectAttachment:
    row = (
        db.query(models.ProjectAttachment)
        .filter_by(project_id=project_id, id=attachment_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return row


def _used_project_bytes(db: Session, project_id: str) -> int:
    used = db.query(func.coalesce(func.sum(models.ProjectAttachment.size_bytes), 0)).filter(
        models.ProjectAttachment.project_id == project_id
    ).scalar()
    return int(used or 0)


@router.post("/{project_id}/attachments", status_code=201)
async def upload_project_attachment(project_id: str, request: Request, db: Session = Depends(get_db)):
    _project_or_404(db, project_id)
    raw_length = request.headers.get("content-length")
    if raw_length:
        try:
            if int(raw_length) > MAX_ATTACHMENT_BYTES + _UPLOAD_HEADER_ALLOWANCE:
                raise HTTPException(status_code=413, detail="Attachment exceeds the 25 MiB file limit")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid Content-Length header") from exc

    # Serialize upload + quota check in this single-user sidecar process. Streaming
    # counts each chunk against both limits, so concurrent requests cannot oversubscribe.
    async with UPLOAD_LOCK:
        try:
            form = await request.form(max_files=1, max_fields=0, max_part_size=MAX_ATTACHMENT_BYTES)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=422, detail="Malformed multipart upload") from exc
        try:
            if set(form.keys()) != {"file"}:
                raise HTTPException(status_code=422, detail="Upload exactly one file in the 'file' field")
            values = form.getlist("file")
            if len(values) != 1 or not isinstance(values[0], UploadFile):
                raise HTTPException(status_code=422, detail="Upload exactly one file in the 'file' field")
            uploaded = values[0]
            original_name = safe_original_name(uploaded.filename)
            declared_mime = (uploaded.content_type or "").strip()[:255] or None
            storage_key = new_storage_key()
            used = _used_project_bytes(db, project_id)
            if used >= MAX_PROJECT_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="Project has reached its 500 MiB upload quota")

            staging: Path | None = None
            promoted = False
            try:
                try:
                    staging, size_bytes, digest = await stream_to_staging(
                        uploaded, storage_key=storage_key, used_project_bytes=used
                    )
                except OverflowError as exc:
                    raise HTTPException(status_code=413, detail=str(exc)) from exc
                except AttachmentStorageError as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc

                try:
                    detected_mime = validate_attachment(staging, original_name, declared_mime)
                except AttachmentStorageError as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc

                scan_result, scanner_version = await scan_attachment(staging)
                if scan_result == "clean":
                    status, clean, scanned_at = "clean", True, datetime.now(timezone.utc)
                elif scan_result == "infected":
                    status, clean, scanned_at = "rejected", False, datetime.now(timezone.utc)
                else:
                    # Scanner absent, timed out, crashed or returned an uncertain verdict:
                    # preserve the file in quarantine, never make it downloadable or runnable.
                    status, clean, scanned_at = "quarantined", False, None

                promote_staged_file(staging, storage_key, clean=clean)
                promoted = True
                row = models.ProjectAttachment(
                    project_id=project_id,
                    storage_key=storage_key,
                    original_name=original_name,
                    declared_mime=declared_mime,
                    detected_mime=detected_mime,
                    size_bytes=size_bytes,
                    sha256=digest,
                    status=status,
                    scanner_version=scanner_version,
                    created_at=datetime.now(timezone.utc),
                    scanned_at=scanned_at,
                )
                db.add(row)
                try:
                    db.commit()
                    db.refresh(row)
                except Exception as exc:
                    db.rollback()
                    raise HTTPException(status_code=500, detail="Attachment metadata could not be saved") from exc
                return attachment_out(row)
            except BaseException:
                if staging is not None:
                    try:
                        if staging.is_file() and not staging.is_symlink():
                            staging.unlink()
                    except OSError:
                        pass
                if promoted:
                    try:
                        remove_attachment_blobs(storage_key)
                    except OSError:
                        pass
                raise
        finally:
            await form.close()


@router.get("/{project_id}/attachments")
def list_project_attachments(
    project_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    _project_or_404(db, project_id)
    try:
        offset = int(cursor or "0")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid attachment cursor") from exc
    if offset < 0:
        raise HTTPException(status_code=422, detail="Invalid attachment cursor")
    rows = (
        db.query(models.ProjectAttachment)
        .filter_by(project_id=project_id)
        .order_by(models.ProjectAttachment.created_at.desc(), models.ProjectAttachment.id.desc())
        .offset(offset)
        .limit(limit + 1)
        .all()
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    return {
        "items": [attachment_out(row) for row in page],
        "next_cursor": str(offset + limit) if has_more else None,
    }


@router.get("/{project_id}/attachments/{attachment_id}")
def get_project_attachment(
    project_id: str, attachment_id: str, db: Session = Depends(get_db)
) -> dict:
    _project_or_404(db, project_id)
    return attachment_out(_lookup_attachment_or_404(db, project_id, attachment_id))


@router.get("/{project_id}/attachments/{attachment_id}/content")
def download_project_attachment(
    project_id: str, attachment_id: str, db: Session = Depends(get_db)
):
    _project_or_404(db, project_id)
    row = _lookup_attachment_or_404(db, project_id, attachment_id)
    if row.status != "clean":
        raise HTTPException(status_code=409, detail="Attachment is quarantined or rejected and cannot be downloaded")
    try:
        path = resolve_blob(row.storage_key, clean=True)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Attachment content not found") from exc
    except AttachmentStorageError as exc:
        raise HTTPException(status_code=500, detail="Attachment storage failed safety checks") from exc
    return FileResponse(
        path=path,
        media_type=row.detected_mime,
        headers={
            "Content-Disposition": content_disposition(row.original_name),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "Cross-Origin-Resource-Policy": "same-origin",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


@router.post("/{project_id}/attachments/{attachment_id}/scan")
async def rescan_project_attachment(
    project_id: str, attachment_id: str, db: Session = Depends(get_db)
) -> dict:
    _project_or_404(db, project_id)
    row = _lookup_attachment_or_404(db, project_id, attachment_id)
    if row.status == "clean":
        return {**attachment_out(row), "scan_result": "already_clean"}
    if row.status != "quarantined":
        raise HTTPException(status_code=409, detail="Only quarantined attachments can be rescanned")

    try:
        path = resolve_blob(row.storage_key, clean=False)
        detected_mime = validate_attachment(path, row.original_name, row.declared_mime)
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        if path.stat().st_size != row.size_bytes or digest.hexdigest() != row.sha256:
            raise AttachmentStorageError("Attachment integrity changed while quarantined")
        if detected_mime != row.detected_mime:
            raise AttachmentStorageError("Attachment MIME changed while quarantined")
    except (FileNotFoundError, OSError):
        row.status = "rejected"
        row.scanned_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=409, detail="Quarantined attachment content is missing")
    except AttachmentStorageError as exc:
        row.status = "rejected"
        row.scanned_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=422, detail="Quarantined attachment failed integrity or format validation") from exc

    scan_result, scanner_version = await scan_attachment(path)
    row.scanner_version = scanner_version
    if scan_result == "clean":
        try:
            promote_quarantined_blob_to_clean(row.storage_key)
        except (AttachmentStorageError, OSError) as exc:
            raise HTTPException(status_code=409, detail="Attachment could not be safely promoted") from exc
        row.status = "clean"
        row.scanned_at = datetime.now(timezone.utc)
    elif scan_result == "infected":
        row.status = "rejected"
        row.scanned_at = datetime.now(timezone.utc)
    # Missing scanner, timeout or an uncertain result remain quarantined.
    try:
        db.commit()
        db.refresh(row)
    except Exception as exc:
        db.rollback()
        if scan_result == "clean":
            # Restore the quarantine location if the metadata update did not commit.
            try:
                from app.infra.attachment_storage import upload_dirs
                _, quarantine, objects = upload_dirs()
                clean_path = objects / f"{row.storage_key}.blob"
                quarantine_path = quarantine / f"{row.storage_key}.blob"
                if clean_path.is_file() and not clean_path.is_symlink() and not quarantine_path.exists():
                    clean_path.replace(quarantine_path)
            except OSError:
                pass
        raise HTTPException(status_code=500, detail="Attachment scan status could not be saved") from exc
    return {**attachment_out(row), "scan_result": scan_result}


@router.delete("/{project_id}/attachments/{attachment_id}")
def delete_project_attachment(
    project_id: str, attachment_id: str, db: Session = Depends(get_db)
) -> dict[str, bool]:
    _project_or_404(db, project_id)
    row = _lookup_attachment_or_404(db, project_id, attachment_id)
    try:
        remove_attachment_blobs(row.storage_key)
    except AttachmentStorageError as exc:
        raise HTTPException(status_code=500, detail="Attachment could not be safely removed; retry deletion") from exc
    db.delete(row)
    db.commit()
    return {"deleted": True}
