"""Local sidecar authentication.

The Electron parent owns a random token and passes it to the child process.
Only /health is unauthenticated. Query-string tokens are intentionally accepted
only for browser APIs that cannot set Authorization headers: WebSockets and
generated-file URLs. Never log the token or a token-bearing URL.
"""
from __future__ import annotations

import hmac
import json
import os
from urllib.parse import parse_qs

from starlette.types import ASGIApp, Message, Receive, Scope, Send


def expected_token() -> str | None:
    value = os.environ.get("AGENTFORGE_TOKEN")
    if value:
        return value
    if os.environ.get("AGENTFORGE_DEV") == "1":
        return os.environ.get("VITE_DEV_TOKEN", "dev")
    return None


def token_is_valid(candidate: str | None) -> bool:
    expected = expected_token()
    return bool(candidate and expected and hmac.compare_digest(candidate, expected))


def require_runtime_token() -> str:
    """Fail startup closed unless Electron supplied a token or explicit dev mode is enabled."""
    token = expected_token()
    if not token:
        raise RuntimeError(
            "AGENTFORGE_TOKEN is required. Set AGENTFORGE_DEV=1 only for local development."
        )
    return token


def _bearer(headers: list[tuple[bytes, bytes]]) -> str | None:
    for key, value in headers:
        if key.lower() == b"authorization":
            raw = value.decode("latin1")
            scheme, _, credential = raw.partition(" ")
            if scheme.lower() == "bearer" and credential:
                return credential
    return None


def _query_token(scope: Scope) -> str | None:
    try:
        query = parse_qs(scope.get("query_string", b"").decode("ascii", errors="ignore"))
    except Exception:
        return None
    values = query.get("token", [])
    return values[0] if values else None


def _allows_query_token(scope: Scope) -> bool:
    if scope["type"] == "websocket":
        return True
    path = scope.get("path", "")
    return path.startswith("/files/") or (
        path.startswith("/v2/executions/") and "/files/" in path
    )


class TokenAuthMiddleware:
    """ASGI middleware covering HTTP, static files and WebSockets."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope_type = scope.get("type")
        if scope_type not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if scope_type == "http" and path == "/health":
            await self.app(scope, receive, send)
            return

        candidate = _bearer(scope.get("headers", []))
        if candidate is None and _allows_query_token(scope):
            candidate = _query_token(scope)

        if token_is_valid(candidate):
            await self.app(scope, receive, send)
            return

        if scope_type == "websocket":
            await send({"type": "websocket.close", "code": 4401, "reason": "Unauthorized"})
            return

        if expected_token() is None:
            status = 503
            detail = "Runtime authentication is not configured"
        else:
            status = 401
            detail = "Missing or invalid bearer token"
        body = json.dumps({"detail": detail}).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        })
        await send({"type": "http.response.body", "body": body})
