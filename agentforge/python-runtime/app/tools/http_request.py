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


async def _mock_request_backend(method: str, url: str, body: str | None) -> str:
    return f"[mock {method} response from {url}] status=200 body_echo={body!r}"


class HttpRequestTool(Tool):
    name = "http_request"
    description = "Make an HTTP GET or POST request to a specified URL."

    def __init__(self, request_fn: RequestFn | None = None):
        self._request_fn = request_fn or _mock_request_backend

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
