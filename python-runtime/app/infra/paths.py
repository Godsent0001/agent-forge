"""Shared data paths for development and packaged runtime."""
from __future__ import annotations

import os
from pathlib import Path

DATA_SUBDIRECTORIES = ("db", "runs", "assets", "queues", "logs", "output", "uploads", "cache", "projects")


def data_dir() -> Path:
    """Return the writable per-user data root, creating its standard subdirectories."""
    configured = os.environ.get("AGENTFORGE_DATA_DIR")
    if configured:
        root = Path(configured).expanduser().resolve()
    else:
        # app/infra/paths.py -> app -> python-runtime
        root = (Path(__file__).resolve().parents[2] / ".data").resolve()
    root.mkdir(parents=True, exist_ok=True)
    for name in DATA_SUBDIRECTORIES:
        (root / name).mkdir(parents=True, exist_ok=True)
    return root
