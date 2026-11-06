import json
import logging
import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.infra.paths import data_dir

logger = logging.getLogger("agentforge.settings")

DEFAULT_EMBEDDING_MODEL = "local:BAAI/bge-small-en-v1.5"


def _embedding_settings_path() -> Path:
    return data_dir() / "embedding_settings.json"


def _valid_embedding_model(value: str) -> bool:
    return bool(value and len(value) <= 200 and not any(char.isspace() for char in value)
                and re.fullmatch(r"[A-Za-z0-9_.:/-]+", value)
                and (value.startswith("local:") or "/" in value))


def _load_embedding_model() -> str:
    configured = os.environ.get("AGENTFORGE_EMBEDDING_MODEL")
    if configured and _valid_embedding_model(configured):
        return configured
    try:
        stored = json.loads(_embedding_settings_path().read_text("utf-8"))
        value = stored.get("model")
        if isinstance(value, str) and _valid_embedding_model(value):
            os.environ["AGENTFORGE_EMBEDDING_MODEL"] = value
            return value
    except (OSError, ValueError, AttributeError):
        pass
    os.environ.setdefault("AGENTFORGE_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
    return os.environ["AGENTFORGE_EMBEDDING_MODEL"]


_CURRENT_EMBEDDING_MODEL = _load_embedding_model()

router = APIRouter(prefix="/settings", tags=["settings"])

# Key slot (what the UI sends) -> environment variables LiteLLM reads for that provider.
# "google" is the slot for Google AI Studio (Gemini); it keeps older saved keys working.
PROVIDER_ENV_VARS: dict[str, tuple[str, ...]] = {
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "google": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "deepseek": ("DEEPSEEK_API_KEY",),
    "mistral": ("MISTRAL_API_KEY",),
    "groq": ("GROQ_API_KEY",),
    "xai": ("XAI_API_KEY",),
    "openrouter": ("OPENROUTER_API_KEY",),
    "venice": ("VENICE_API_KEY",),
    "serper": ("SERPER_API_KEY",),
}


@router.post("/keys")
def set_api_keys(payload: dict[str, str | None]):
    """Set (non-empty value) or clear (empty string) provider keys in this process's environment. Unknown slots are ignored."""
    updated: list[str] = []
    ignored: list[str] = []
    for slot, value in payload.items():
        env_vars = PROVIDER_ENV_VARS.get(slot)
        if env_vars is None:
            ignored.append(slot)
            continue
        if value is None:
            continue
        for name in env_vars:
            if value:
                os.environ[name] = value
            else:
                os.environ.pop(name, None)
        updated.append(f"{slot} ({'set' if value else 'cleared'})")  # never log key material, not even its length

    logger.info("API keys updated in runtime environment: %s", ", ".join(updated) if updated else "none")
    if ignored:
        logger.warning("Ignored keys for unsupported providers: %s", ", ".join(ignored))
    return {"status": "ok"}


@router.get("/keys")
def get_api_keys_status():
    """Which providers currently have a key in the runtime. Never returns the keys themselves."""
    return {slot: any(os.environ.get(name) for name in names) for slot, names in PROVIDER_ENV_VARS.items()}



@router.get("/embedding-model")
def get_embedding_model():
    """Return the configured embedding model identifier (never returns credentials)."""
    return {"model": os.environ.get("AGENTFORGE_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)}


@router.post("/embedding-model")
def set_embedding_model(payload: dict[str, str]):
    """Set a local or LiteLLM provider/model identifier for future memory retrieval."""
    value = payload.get("model", "").strip()
    if not _valid_embedding_model(value):
        raise HTTPException(
            status_code=422,
            detail="Use 'local:MODEL_ID' or a provider/model identifier, without spaces.",
        )
    path = _embedding_settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps({"model": value}, indent=2), encoding="utf-8")
        temporary.replace(path)
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Could not persist embedding model configuration.") from exc
    os.environ["AGENTFORGE_EMBEDDING_MODEL"] = value
    logger.info("Embedding model configuration updated: %s", value)
    return {"status": "ok", "model": value}


@router.post("/search/test")
async def test_search_provider():
    """Perform a real Serper query without returning or logging the API key."""
    if not os.environ.get("SERPER_API_KEY", "").strip():
        raise HTTPException(status_code=400, detail="Serper API key is not configured.")
    try:
        from app.tools.web_search import _serper_search_backend

        results = await _serper_search_backend("AgentForge web search connection test")
    except Exception as exc:
        message = str(exc)
        status_code = 502
        if "API key" in message or "SERPER_API_KEY" in message:
            status_code = 401
        elif "quota" in message or "rate limit" in message:
            status_code = 429
        logger.warning("Serper connection test failed: %s", type(exc).__name__)
        raise HTTPException(status_code=status_code, detail=message[:300]) from exc
    return {"status": "ok", "provider": "serper", "results": len(results)}
