from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTFORGE_TOKEN", "file-route-test-token")
    monkeypatch.delenv("AGENTFORGE_DEV", raising=False)
    monkeypatch.setenv("AGENTFORGE_DATA_DIR", str(tmp_path / "user-data"))
    root = tmp_path / "user-data" / "output"
    root.mkdir(parents=True)
    return TestClient(main.app)


def test_legacy_file_route_requires_token(client, tmp_path):
    (tmp_path / "user-data" / "output" / "safe.txt").write_text("content", encoding="utf-8")
    assert client.get("/files/safe.txt").status_code == 401
    assert client.get("/files/safe.txt?token=wrong").status_code == 401
    response = client.get("/files/safe.txt?token=file-route-test-token")
    assert response.status_code == 200
    assert response.text == "content"


def test_legacy_active_content_is_forced_to_download(client, tmp_path):
    (tmp_path / "user-data" / "output" / "preview.html").write_text("<script>alert(1)</script>", encoding="utf-8")
    response = client.get("/files/preview.html?token=file-route-test-token")
    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith("attachment")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in response.headers["content-security-policy"]


def test_legacy_file_route_rejects_symlink_escape(client, tmp_path):
    outside = tmp_path / "secret.txt"
    outside.write_text("do-not-serve", encoding="utf-8")
    (tmp_path / "user-data" / "output" / "escape.txt").symlink_to(outside)
    response = client.get("/files/escape.txt?token=file-route-test-token")
    assert response.status_code == 404
