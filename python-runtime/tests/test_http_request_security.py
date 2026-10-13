from __future__ import annotations

import socket
from types import SimpleNamespace

import httpx
import pytest

from app.infra.ssrf import UnsafeURL, assert_public_url
from app.tools.base import ToolExecutionError
from app.tools.http_request import MAX_RESPONSE_BYTES, HttpRequestTool, _app_port, _real_request_backend


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8000/health",
    "http://localhost/",
    "http://169.254.169.254/",
    "http://10.0.0.1/",
    "http://[::1]/",
    "file:///etc/passwd",
    "ftp://example.com/",
    "https://user:secret@example.com/",
])
def test_ssrf_guard_rejects_local_special_or_non_http_urls(url):
    with pytest.raises(UnsafeURL):
        assert_public_url(url, app_port=8000)


def test_ssrf_guard_allows_public_literal_ip():
    assert_public_url("https://8.8.8.8/")



def test_ssrf_guard_uses_the_actual_runtime_port(monkeypatch):
    monkeypatch.setenv("AGENTFORGE_PORT", "9123")
    assert _app_port() == 9123
    with pytest.raises(UnsafeURL):
        assert_public_url("http://8.8.8.8:9123/", app_port=_app_port())


@pytest.mark.asyncio
async def test_http_tool_refuses_private_target_before_calling_backend():
    called = False

    async def fake_request(method, url, body):
        nonlocal called
        called = True
        return "unexpected"

    tool = HttpRequestTool(request_fn=fake_request)
    with pytest.raises(ToolExecutionError, match="private|local"):
        await tool.execute("GET http://127.0.0.1:8000/health", context=SimpleNamespace())
    assert called is False


@pytest.mark.asyncio
async def test_redirect_to_private_target_is_rejected(monkeypatch):
    def fake_dns(host, port, type):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]
    monkeypatch.setattr("app.infra.ssrf.socket.getaddrinfo", fake_dns)

    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(
            302,
            headers={"Location": "http://127.0.0.1:8000/health"},
            request=request,
        )

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    def mock_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)
    monkeypatch.setattr(httpx, "AsyncClient", mock_client)

    tool = HttpRequestTool()
    with pytest.raises(ToolExecutionError, match="private|local"):
        await tool.execute("GET https://example.com/start", context=SimpleNamespace())
    assert calls == ["https://example.com/start"]


@pytest.mark.asyncio
async def test_http_response_body_is_capped_at_one_megabyte(monkeypatch):
    def handler(request):
        return httpx.Response(200, content=b"x" * (MAX_RESPONSE_BYTES + 100), request=request)

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    def mock_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)
    monkeypatch.setattr(httpx, "AsyncClient", mock_client)
    monkeypatch.setattr("app.infra.ssrf.socket.getaddrinfo", lambda host, port, type: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))
    ])

    result = await _real_request_backend("GET", "https://example.com/file", None)
    body = result.split("\nBody:\n", 1)[1].split("\n…[truncated]", 1)[0]
    assert len(body) == MAX_RESPONSE_BYTES
    assert "truncated: true" in result
