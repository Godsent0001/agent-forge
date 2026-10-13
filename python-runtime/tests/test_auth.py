from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app
from app.infra.auth import TokenAuthMiddleware, _allows_query_token


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("AGENTFORGE_TOKEN", "test-secret-token")
    monkeypatch.delenv("AGENTFORGE_DEV", raising=False)
    return TestClient(app)


def test_health_is_public(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_api_requires_bearer_token(client):
    response = client.get("/settings/keys")
    assert response.status_code == 401
    assert response.json()["detail"] == "Missing or invalid bearer token"


def test_valid_bearer_token_is_accepted(client):
    response = client.get("/settings/keys", headers={"Authorization": "Bearer test-secret-token"})
    assert response.status_code == 200
    assert "anthropic" in response.json()


def test_wrong_bearer_token_is_rejected(client):
    response = client.get("/settings/keys", headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


def test_query_token_is_not_accepted_for_regular_api(client):
    response = client.get("/settings/keys?token=test-secret-token")
    assert response.status_code == 401


def test_websocket_without_token_is_rejected(client):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect("/v2/executions/not-a-run/stream"):
            pass
    assert error.value.code == 4401


@pytest.mark.asyncio
async def test_valid_websocket_query_token_passes_auth_middleware(monkeypatch):
    monkeypatch.setenv("AGENTFORGE_TOKEN", "test-secret-token")
    messages = []

    async def inner(scope, receive, send):
        await send({"type": "websocket.accept"})
        await send({"type": "websocket.close", "code": 1000})

    async def receive():
        return {"type": "websocket.connect"}

    async def send(message):
        messages.append(message)

    middleware = TokenAuthMiddleware(inner)
    await middleware(
        {
            "type": "websocket",
            "path": "/v2/executions/run/stream",
            "query_string": b"token=test-secret-token",
            "headers": [],
        },
        receive,
        send,
    )
    assert messages[0]["type"] == "websocket.accept"
    assert messages[1]["code"] == 1000


def test_query_tokens_are_scoped_to_websocket_and_file_routes():
    assert _allows_query_token({"type": "websocket", "path": "/anything"})
    assert _allows_query_token({"type": "http", "path": "/files/result.png"})
    assert _allows_query_token({"type": "http", "path": "/v2/executions/run/files/result.png"})
    assert not _allows_query_token({"type": "http", "path": "/v2/executions/run"})
    assert not _allows_query_token({"type": "http", "path": "/projects"})
    

def test_cors_rejects_unapproved_origin(client):
    response = client.options(
        "/projects",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert "access-control-allow-origin" not in response.headers
