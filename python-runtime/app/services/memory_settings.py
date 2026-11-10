"""Persistent privacy controls for semantic memory retrieval."""
import json
from pathlib import Path

from app.infra.paths import data_dir


def memory_settings_path() -> Path:
    return data_dir() / "memory_settings.json"


def cross_conversation_memory_enabled() -> bool:
    """Cross-conversation recall is privacy-sensitive and remains opt-in."""
    try:
        stored = json.loads(memory_settings_path().read_text("utf-8"))
        return stored.get("cross_conversation_enabled") is True
    except (OSError, ValueError, AttributeError):
        return False


def save_cross_conversation_memory(enabled: bool) -> None:
    path = memory_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps({"cross_conversation_enabled": enabled}, indent=2), encoding="utf-8")
    temporary.replace(path)
