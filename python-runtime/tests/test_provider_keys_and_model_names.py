import importlib.util
import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.routers import settings as settings_router  # noqa: E402

# Load model_names directly so this test does not import the heavy LiteLLM-dependent runner.
spec = importlib.util.spec_from_file_location("model_names", ROOT / "app" / "core" / "llm" / "model_names.py")
model_names = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model_names)

ALL_VARS = [v for names in settings_router.PROVIDER_ENV_VARS.values() for v in names]


def client(monkeypatch):
    for name in ALL_VARS:
        monkeypatch.delenv(name, raising=False)
    app = FastAPI()
    app.include_router(settings_router.router)
    return TestClient(app)


def test_sets_keys_for_new_providers(monkeypatch):
    c = client(monkeypatch)
    r = c.post("/settings/keys", json={"deepseek": "sk-ds", "groq": "gsk-1", "anthropic": "sk-ant"})
    assert r.status_code == 200
    assert os.environ["DEEPSEEK_API_KEY"] == "sk-ds"
    assert os.environ["GROQ_API_KEY"] == "gsk-1"
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant"
    c.post("/settings/keys", json={"venice": "venice-test-key"})
    assert os.environ["VENICE_API_KEY"] == "venice-test-key"


def test_google_slot_sets_both_gemini_variables(monkeypatch):
    c = client(monkeypatch)
    c.post("/settings/keys", json={"google": "AIza-test"})
    assert os.environ["GEMINI_API_KEY"] == "AIza-test"
    assert os.environ["GOOGLE_API_KEY"] == "AIza-test"


def test_empty_string_clears_a_key(monkeypatch):
    c = client(monkeypatch)
    c.post("/settings/keys", json={"openai": "sk-x"})
    assert c.get("/settings/keys").json()["openai"] is True
    c.post("/settings/keys", json={"openai": ""})
    assert "OPENAI_API_KEY" not in os.environ
    assert c.get("/settings/keys").json()["openai"] is False


def test_null_leaves_existing_key_untouched(monkeypatch):
    c = client(monkeypatch)
    c.post("/settings/keys", json={"openai": "sk-x"})
    c.post("/settings/keys", json={"openai": None})
    assert os.environ["OPENAI_API_KEY"] == "sk-x"


def test_unknown_providers_are_ignored_not_errors(monkeypatch):
    c = client(monkeypatch)
    r = c.post("/settings/keys", json={"not-a-provider": "x", "mistral": "m-1"})
    assert r.status_code == 200
    assert os.environ["MISTRAL_API_KEY"] == "m-1"


def test_status_reports_every_slot_and_never_returns_keys(monkeypatch):
    c = client(monkeypatch)
    c.post("/settings/keys", json={"xai": "secret-value"})
    body = c.get("/settings/keys").json()
    assert set(body) == set(settings_router.PROVIDER_ENV_VARS)
    assert body["xai"] is True and body["deepseek"] is False
    assert body["venice"] is False
    assert "secret-value" not in c.get("/settings/keys").text


def test_litellm_model_names():
    f = model_names.litellm_model
    assert f("anthropic", "claude-sonnet-5-5") == "anthropic/claude-sonnet-5-5"
    assert f("gemini", "gemini-2.5-flash") == "gemini/gemini-2.5-flash"
    assert f("google", "gemini-2.5-flash") == "gemini/gemini-2.5-flash"  # older agents
    assert f("deepseek", "deepseek-chat") == "deepseek/deepseek-chat"
    assert f("openrouter", "anthropic/claude-sonnet-4.5") == "openrouter/anthropic/claude-sonnet-4.5"
    assert f(None, "gpt-4o") == "gpt-4o"
    assert f("", "gpt-4o") == "gpt-4o"
