from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.contracts.run import MemoryOptions
from app.routers.settings import router


def test_embedding_model_setting_persists_and_applies_to_new_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTFORGE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("AGENTFORGE_EMBEDDING_MODEL", raising=False)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post("/settings/embedding-model", json={"model": "venice/text-embedding-bge-m3"})
    assert response.status_code == 200
    assert response.json()["model"] == "venice/text-embedding-bge-m3"
    assert client.get("/settings/embedding-model").json()["model"] == "venice/text-embedding-bge-m3"
    assert MemoryOptions().embedding_model == "venice/text-embedding-bge-m3"
    assert (tmp_path / "embedding_settings.json").is_file()


def test_embedding_model_setting_rejects_invalid_identifiers(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTFORGE_DATA_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).post("/settings/embedding-model", json={"model": "bad model"})
    assert response.status_code == 422
