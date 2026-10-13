"""HTTP request tool with SSRF-safe, bounded, manually validated redirects.

Input format: "GET <url>" or "POST <url>::<body>".
DNS rebinding between validation and connection is a known limitation.
"""
from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urljoin

from app.infra.ssrf import UnsafeURL, assert_public_url
from app.tools.base import Tool, ToolExecutionError

RequestFn = Callable[[str, str, str | None], Awaitable[str]]
MAX_RESPONSE_BYTES = 1_000_000
MAX_REDIRECTS = 5
DEFAULT_APP_PORT = 8000


def _app_port() -> int:
    """Resolve the runtime's actual bound port, including local custom-port launches."""
    raw = os.environ.get("AGENTFORGE_PORT") or os.environ.get("PORT")
    try:
        value = int(raw) if raw else DEFAULT_APP_PORT
    except ValueError:
        value = DEFAULT_APP_PORT
    return value if 1 <= value <= 65535 else DEFAULT_APP_PORT


async def _real_request_backend(method: str, url: str, body: str | None) -> str:
    import httpx

    current_url = url
    current_method = method
    current_body = body
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=False, trust_env=False) as client:
        for redirect_count in range(MAX_REDIRECTS + 1):
            assert_public_url(current_url, app_port=_app_port())
            headers = (
                {"Content-Type": "application/json"}
                if current_body and current_body.strip().startswith(("{", "["))
                else None
            )
            async with client.stream(
                current_method, current_url, content=current_body, headers=headers
            ) as resp:
                if resp.status_code in {301, 302, 303, 307, 308}:
                    location = resp.headers.get("location")
                    if not location:
                        return f"Status: {resp.status_code}\\nRedirect response had no Location header."
                    if redirect_count >= MAX_REDIRECTS:
                        raise ToolExecutionError("HTTP request exceeded 5 redirects")
                    next_url = urljoin(current_url, location)
                    assert_public_url(next_url, app_port=_app_port())
                    if resp.status_code == 303 or (
                        resp.status_code in {301, 302} and current_method == "POST"
                    ):
                        current_method, current_body = "GET", None
                    current_url = next_url
                    continue

                chunks: list[bytes] = []
                total = 0
                truncated = False
                async for chunk in resp.aiter_bytes():
                    remaining = MAX_RESPONSE_BYTES - total
                    if len(chunk) > remaining:
                        chunks.append(chunk[:remaining])
                        total += remaining
                        truncated = True
                        break
                    chunks.append(chunk)
                    total += len(chunk)
                    if total >= MAX_RESPONSE_BYTES:
                        truncated = True
                        break

                text = b"".join(chunks).decode(resp.encoding or "utf-8", errors="replace")
                header_lines = "\\n".join(
                    f"{key}: {value}" for key, value in resp.headers.items()
                    if key.lower() not in {"set-cookie", "authorization", "proxy-authorization"}
                )
                suffix = "\\n…[truncated]" if truncated else ""
                return (
                    f"Status: {resp.status_code}\\nHeaders:\\n{header_lines}"
                    f"\\nBody:\\n{text}{suffix}\\ntruncated: {str(truncated).lower()}"
                )

    raise ToolExecutionError("HTTP redirect handling failed")


class HttpRequestTool(Tool):
    name = "http_request"
    description = "Make an HTTP GET or POST request to a public URL."

    def __init__(self, request_fn: RequestFn | None = None):
        self._request_fn = request_fn or _real_request_backend

    async def execute(self, input: str, *, context: Any) -> str:
        parts = input.split(" ", 1)
        if len(parts) != 2 or parts[0] not in ("GET", "POST"):
            raise ToolExecutionError("Input must be 'GET <url>' or 'POST <url>::<body>'")

        method, rest = parts
        url, _, body = rest.partition("::")
        try:
            assert_public_url(url, app_port=APP_PORT)
            return await self._request_fn(method, url, body or None)
        except UnsafeURL as exc:
            raise ToolExecutionError(str(exc)) from exc
        except ToolExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ToolExecutionError(f"http_request failed: {exc}") from exc
