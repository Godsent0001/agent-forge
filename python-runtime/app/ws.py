"""
Phase 7 — live execution events over WebSocket.

Design: one broadcast channel per execution_id. The frontend connects to
/ws/executions/{execution_id} right after POSTing /executions, and
receives every ExecutionEvent as it happens, in order. This is additive
to DB persistence (engine.py's sink writes to SQLite AND broadcasts here)
so a client that connects late can still fetch prior events via
GET /executions/{id}/events and reconcile.
"""

from __future__ import annotations

import json
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, execution_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections[execution_id].append(ws)

    def disconnect(self, execution_id: str, ws: WebSocket) -> None:
        conns = self._connections.get(execution_id, [])
        if ws in conns:
            conns.remove(ws)

    async def broadcast(self, execution_id: str, payload: dict) -> None:
        dead: list[WebSocket] = []
        for ws in self._connections.get(execution_id, []):
            try:
                await ws.send_text(json.dumps(payload))
            except Exception:  # noqa: BLE001 — a dead socket shouldn't break the run
                dead.append(ws)
        for ws in dead:
            self.disconnect(execution_id, ws)


manager = ConnectionManager()
