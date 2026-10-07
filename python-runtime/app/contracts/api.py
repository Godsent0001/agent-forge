"""C-8 response shapes that are not core types. Platform-owned data (see docs/CONTRACTS.md)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

NotificationKind = Literal["intent_due", "insight_ready", "maintenance_failed"]
MaintenanceKind = Literal["dream", "embed_backfill"]


class Notification(BaseModel):
    id: str
    kind: NotificationKind
    title: str
    body: str = ""
    ref_id: str | None = None
    created_at: datetime
    read_at: datetime | None = None


class MaintenanceRun(BaseModel):
    id: str
    kind: MaintenanceKind
    started_at: datetime
    ended_at: datetime | None = None
    status: Literal["running", "ok", "error"] = "running"
    cost_usd: float | None = None
    detail: dict = {}


class ModelInfo(BaseModel):
    provider: str
    model: str
    tier: str
    kind: Literal["chat", "embedding"] = "chat"
    context_window: int | None = None
    supports_tools: bool = False
    supports_vision: bool = False
    price_in: float | None = None            # USD per million input tokens; 0.0 for local models, None = unknown
    price_out: float | None = None
