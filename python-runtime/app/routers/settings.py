from fastapi import APIRouter
from pydantic import BaseModel
import os
import logging

logger = logging.getLogger("agentforge.settings")

router = APIRouter(prefix="/settings", tags=["settings"])

class APIKeysPayload(BaseModel):
    anthropic: str | None = None
    openai: str | None = None
    google: str | None = None

@router.post("/keys")
def set_api_keys(payload: APIKeysPayload):
    updated = []
    if payload.google is not None:
        os.environ["GEMINI_API_KEY"] = payload.google
        os.environ["GOOGLE_API_KEY"] = payload.google
        updated.append(f"google (len={len(payload.google)})")
    if payload.openai is not None:
        os.environ["OPENAI_API_KEY"] = payload.openai
        updated.append(f"openai (len={len(payload.openai)})")
    if payload.anthropic is not None:
        os.environ["ANTHROPIC_API_KEY"] = payload.anthropic
        updated.append(f"anthropic (len={len(payload.anthropic)})")

    logger.info(f"API keys updated in runtime environment: {', '.join(updated) if updated else 'none'}")
    return {"status": "ok"}

@router.get("/keys")
def get_api_keys_status():
    return {
        "google": bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")),
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
    }
