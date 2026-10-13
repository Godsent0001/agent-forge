"""Machine-readable dependency and runtime readiness checks for Settings."""
from __future__ import annotations

import importlib.util
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.db import SessionLocal
from app.infra.paths import data_dir
from app.routers.settings import PROVIDER_ENV_VARS

router = APIRouter(prefix="/v2/system", tags=["system"])
MIN_FREE_BYTES = 1_000_000_000


class SystemCheck(BaseModel):
    name: str
    ok: bool
    detail: str
    fix: str | None = None


def _binary_check(name: str, hint: str) -> SystemCheck:
    path = shutil.which(name)
    return SystemCheck(name=name, ok=path is not None, detail="Available" if path else "Not found on PATH", fix=None if path else hint)


def build_system_checks(root: Path | None = None) -> list[SystemCheck]:
    root = (root or data_dir()).expanduser().resolve()
    checks: list[SystemCheck] = []
    checks.append(_binary_check("ffmpeg", "Install FFmpeg and ensure ffmpeg is available on PATH."))
    checks.append(_binary_check("ffprobe", "Install the FFmpeg package containing ffprobe and ensure it is available on PATH."))
    checks.append(_binary_check("piper", "Install Piper TTS and add the piper executable to PATH. This is optional unless you use Voice Generator."))
    for module, fix in (
        ("matplotlib", "Install the optional video/visualization dependencies for this runtime."),
        ("ddgs", "Install the optional search dependencies for this runtime."),
    ):
        try:
            available = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError):
            available = False
        checks.append(SystemCheck(name=f"python:{module}", ok=available, detail="Available" if available else "Package not installed", fix=None if available else fix))
    checks.extend(
        SystemCheck(
            name=f"provider-key:{slot}",
            ok=any(os.environ.get(variable) for variable in variables),
            detail="Key present in runtime" if any(os.environ.get(variable) for variable in variables) else "No key active in runtime",
            fix=None if any(os.environ.get(variable) for variable in variables) else f"Save a {slot} provider key in Settings or configure its environment variable.",
        )
        for slot, variables in PROVIDER_ENV_VARS.items()
    )
    try:
        root.mkdir(parents=True, exist_ok=True)
        fd, probe = tempfile.mkstemp(prefix=".write-check-", dir=root)
        os.close(fd)
        Path(probe).unlink(missing_ok=True)
        writable = True
    except OSError:
        writable = False
    checks.append(SystemCheck(name="data-directory", ok=writable, detail="Writable" if writable else "Not writable", fix=None if writable else "Choose a writable AGENTFORGE_DATA_DIR and restart the app."))
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1")).scalar_one()
        reachable = True
    except Exception:
        reachable = False
    checks.append(SystemCheck(name="database", ok=reachable, detail="Connected" if reachable else "Connection failed", fix=None if reachable else "Check the runtime database path and disk permissions."))
    try:
        free_bytes = shutil.disk_usage(root).free
        enough_space = free_bytes >= MIN_FREE_BYTES
        detail = f"{free_bytes // (1024 * 1024)} MiB free"
    except OSError:
        enough_space = False
        detail = "Could not determine free disk space"
    checks.append(SystemCheck(name="disk-space", ok=enough_space, detail=detail, fix=None if enough_space else "Free at least 1 GB on the drive storing AgentForge data."))
    return checks


@router.get("/check", response_model=list[SystemCheck])
def system_check() -> list[SystemCheck]:
    return build_system_checks()
