"""Browse and download persistent project workspace files."""
from __future__ import annotations

import os
import re
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app import models
from app.deps import get_db
from app.infra.paths import data_dir, project_dir

router = APIRouter(prefix="/projects", tags=["project-workspace"])
IGNORED_DIRS = {".agentforge", ".git", "node_modules", "__pycache__", ".venv"}
MAX_FILES = 20_000
MAX_TOTAL_BYTES = 512 * 1024 * 1024


def _workspace(project_id: str, db: Session) -> Path:
    if db.get(models.Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        root = (project_dir(project_id) / "workspace").resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="Project workspace is unavailable") from exc


def _files(root: Path) -> list[tuple[Path, str, int]]:
    entries: list[tuple[Path, str, int]] = []
    total = 0
    for current, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [name for name in dirs if name not in IGNORED_DIRS]
        base = Path(current)
        for name in names:
            path = base / name
            if path.is_symlink() or not path.is_file():
                continue
            try:
                resolved = path.resolve()
                rel = resolved.relative_to(root.resolve()).as_posix()
                size = resolved.stat().st_size
            except (OSError, ValueError):
                continue
            if rel.startswith(".results/"):
                # Keep shell logs available in AgentForge, but out of deliverable ZIPs.
                continue
            entries.append((resolved, rel, size))
            total += size
            if len(entries) > MAX_FILES or total > MAX_TOTAL_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail="Project workspace is too large to package (limit: 20,000 files / 512 MiB).",
                )
    return sorted(entries, key=lambda item: item[1].casefold())


@router.get("/{project_id}/workspace")
def list_project_workspace(project_id: str, db: Session = Depends(get_db)):
    root = _workspace(project_id, db)
    files = _files(root)
    return {
        "project_id": project_id,
        "workspace_path": str(root),
        "files": [{"path": rel, "size_bytes": size} for _, rel, size in files],
        "file_count": len(files),
        "total_bytes": sum(size for _, _, size in files),
    }


@router.get("/{project_id}/workspace.zip")
def download_project_workspace(project_id: str, db: Session = Depends(get_db)):
    root = _workspace(project_id, db)
    files = _files(root)
    if not files:
        raise HTTPException(status_code=404, detail="Project workspace is empty")
    cache = data_dir() / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    fd, archive_path = tempfile.mkstemp(prefix="agentforge-project-", suffix=".zip", dir=str(cache))
    os.close(fd)
    try:
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path, relative, _size in files:
                archive.write(path, arcname=relative)
    except Exception:
        try:
            os.unlink(archive_path)
        except OSError:
            pass
        raise
    safe_project = re.sub(r"[^A-Za-z0-9_-]", "_", project_id)[:64]
    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename=f"agentforge-project-{safe_project}.zip",
        background=BackgroundTask(lambda: os.path.exists(archive_path) and os.unlink(archive_path)),
    )
