import logging
import os

from fastapi import APIRouter

logger = logging.getLogger("agentforge.settings")

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
