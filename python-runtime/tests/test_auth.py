from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from main import app


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
    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect("/v2/executions/not-a-run/stream"):
            pass
    assert error.value.code == 4401


def test_websocket_accepts_query_token(client):
    # Auth succeeds, then this route immediately closes an unknown run's event flow only if
    # the test context exits. It is enough to establish the authenticated WS handshake.
    with client.websocket_connect("/v2/executions/not-a-run/stream?token=test-secret-token") as ws:
        ws.close()


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
