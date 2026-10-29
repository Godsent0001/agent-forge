"""Browse and download persistent project workspace files."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
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


@router.get("/{project_id}/workspace/file")
def read_project_workspace_file(
    project_id: str,
    path: str = Query(min_length=1, max_length=1024),
    db: Session = Depends(get_db),
):
    """Serve one file from a project's workspace without allowing path escape."""
    root = _workspace(project_id, db)
    try:
        relative = Path(path)
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise ValueError("invalid relative path")
        candidate = root
        for part in relative.parts:
            candidate = candidate / part
            if candidate.is_symlink():
                raise ValueError("symlinks are not served")
        candidate = candidate.resolve(strict=True)
        candidate.relative_to(root.resolve())
    except (OSError, ValueError):
        raise HTTPException(status_code=404, detail="Workspace file not found") from None

    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Workspace file not found")

    # Active content is marked as an attachment by file_response_headers. The
    # renderer may fetch it as a Blob and show it only inside a sandboxed viewer.
    from app.infra.file_security import file_response_headers
    return FileResponse(path=candidate, headers=file_response_headers(candidate))


@router.post("/{project_id}/workspace/open")
def open_project_workspace(project_id: str, db: Session = Depends(get_db)):
    """Open the current project's workspace in the operating-system file manager."""
    root = _workspace(project_id, db)
    try:
        if os.name == "nt":
            os.startfile(str(root))  # type: ignore[attr-defined]
        else:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            executable = shutil.which(opener)
            if not executable:
                raise OSError(f"File-manager opener '{opener}' is unavailable")
            subprocess.Popen(
                [executable, str(root)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not open project folder: {exc}") from exc
    return {"opened": True, "workspace_path": str(root)}


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
