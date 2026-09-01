"""
HTTP Request tool. Uses a pluggable `request_fn` for the same reason as
web_search: this sandbox has no network access to test a real call, so a
mock is wired by default. Swap in httpx.AsyncClient behind the same
signature when running for real.

Input format: "GET <url>" or "POST <url>::<body>"
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.tools.base import Tool, ToolExecutionError

RequestFn = Callable[[str, str, str | None], Awaitable[str]]


async def _real_request_backend(method: str, url: str, body: str | None) -> str:
    import httpx

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        if method == "GET":
            resp = await client.get(url)
        elif method == "POST":
            headers = {"Content-Type": "application/json"} if body and body.strip().startswith(("{", "[")) else None
            resp = await client.post(url, content=body, headers=headers)
        else:
            raise ValueError(f"Unsupported method: {method}")

        content_preview = resp.text[:2000] + ("..." if len(resp.text) > 2000 else "")
        return f"Status: {resp.status_code}\nHeaders: {dict(resp.headers)}\nBody:\n{content_preview}"


class HttpRequestTool(Tool):
    name = "http_request"
    description = "Make an HTTP GET or POST request to a specified URL."

    def __init__(self, request_fn: RequestFn | None = None):
        self._request_fn = request_fn or _real_request_backend

    async def execute(self, input: str, *, context: Any) -> str:
        parts = input.split(" ", 1)
        if len(parts) != 2 or parts[0] not in ("GET", "POST"):
            raise ToolExecutionError("Input must be 'GET <url>' or 'POST <url>::<body>'")

        method, rest = parts
        url, _, body = rest.partition("::")
        if not url.startswith(("http://", "https://")):
            raise ToolExecutionError(f"Refusing non-HTTP(S) URL: {url}")

        try:
            return await self._request_fn(method, url, body or None)
        except Exception as e:  # noqa: BLE001
            raise ToolExecutionError(f"http_request failed: {e}") from e
