"""Workspace-scoped paths for tools and per-run artifacts.

Tool inputs are always relative paths. Resolution checks both lexical path
components and the final resolved path so traversal and symlink escapes fail.
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any

from app.tools.base import ToolExecutionError


def data_dir() -> Path:
    configured = os.environ.get("AGENTFORGE_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    # Until the shared data-dir task lands, keep dev data under python-runtime.
    return (Path(__file__).resolve().parents[2] / ".data").resolve()


def safe_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
        raise ToolExecutionError("Invalid identifier; use 1-64 letters, digits, '_' or '-'")
    return value


def _relative_parts(rel: str | os.PathLike[str]) -> Path:
    raw = os.fspath(rel)
    if not raw or not raw.strip():
        raise ToolExecutionError("A relative path is required")
    # Reject Windows absolute paths and drive letters even when running on POSIX.
    if raw.startswith(("/", "\\\\")) or re.match(r"^[A-Za-z]:", raw):
        raise ToolExecutionError("Absolute paths are not allowed")
    normalized = raw.replace("\\\\", "/")
    parts = normalized.split("/")
    if any(part == ".." for part in parts):
        raise ToolExecutionError("Parent-directory traversal is not allowed")
    return Path(*[part for part in parts if part not in ("", ".")])


def _within(root: Path, candidate: Path) -> Path:
    resolved_root = root.resolve()
    resolved = candidate.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ToolExecutionError("Path escapes the allowed workspace")
    return resolved


class RunWorkspace:
    """Filesystem scope for a single execution plus read-only shared assets."""

    def __init__(self, execution_id: str, *, root: Path | None = None, assets_root: Path | None = None):
        safe_id(execution_id)
        base = data_dir()
        self.root = (root or (base / "runs" / execution_id)).resolve()
        self.assets_root = (assets_root or (base / "assets")).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.assets_root.mkdir(parents=True, exist_ok=True)

    def resolve(self, rel: str | os.PathLike[str]) -> Path:
        parts = _relative_parts(rel)
        return _within(self.root, self.root / parts)

    def asset(self, rel: str | os.PathLike[str]) -> Path:
        parts = _relative_parts(rel)
        return _within(self.assets_root, self.assets_root / parts)

    def new_path(self, name: str) -> Path:
        """Allocate a unique workspace-relative output path and create parents."""
        parts = _relative_parts(name)
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", parts.name).strip("._") or "output"
        parent = self.resolve(str(parts.parent)) if str(parts.parent) != "." else self.root
        parent.mkdir(parents=True, exist_ok=True)
        stem, suffix = Path(safe_name).stem, Path(safe_name).suffix
        candidate = parent / safe_name
        index = 2
        while candidate.exists():
            candidate = parent / f"{stem}_{index}{suffix}"
            index += 1
        return _within(self.root, candidate)

    def relative(self, path: str | os.PathLike[str]) -> str:
        resolved = _within(self.root, Path(path))
        return resolved.relative_to(self.root.resolve()).as_posix()


def workspace_from(context: Any) -> RunWorkspace:
    """Use the run workspace, with a temporary legacy fallback until S-04."""
    workspace = getattr(context, "workspace", None)
    if isinstance(workspace, RunWorkspace):
        return workspace
    fallback = Path("./output").resolve()
    fallback.mkdir(parents=True, exist_ok=True)
    return RunWorkspace("legacy", root=fallback)


def out_path(context: Any, params: dict[str, Any], key: str, default_name: str) -> Path:
    workspace = workspace_from(context)
    requested = params.get(key) or default_name
    path = workspace.resolve(str(requested))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def in_path(context: Any, params: dict[str, Any], key: str) -> Path:
    workspace = workspace_from(context)
    requested = params.get(key)
    if not isinstance(requested, str) or not requested:
        raise ToolExecutionError(f"Missing required relative path: {key}")
    path = workspace.resolve(requested)
    if not path.is_file():
        raise ToolExecutionError(f"Workspace file does not exist: {requested}")
    return path
