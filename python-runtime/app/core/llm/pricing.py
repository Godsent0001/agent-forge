"""Model catalog and token pricing logic for AgentForge Core."""
from pathlib import Path
from typing import Any

import yaml

from .types import Usage

_MODELS_CACHE: dict[str, dict[str, Any]] | None = None


def _load_models() -> dict[str, dict[str, Any]]:
    global _MODELS_CACHE
    if _MODELS_CACHE is not None:
        return _MODELS_CACHE

    models_map: dict[str, dict[str, Any]] = {}
    yaml_path = Path(__file__).parent / "models.yaml"
    if yaml_path.is_file():
        try:
            data = yaml.safe_load(yaml_path.read_text("utf-8")) or {}
            for item in data.get("models", []):
                full_name = f"{item['provider']}/{item['model']}" if "provider" in item else item['model']
                models_map[full_name] = item
                # Also index by plain model name
                models_map[item['model']] = item
        except Exception:
            pass

    _MODELS_CACHE = models_map
    return _MODELS_CACHE


def get_model_info(model_name: str) -> dict[str, Any] | None:
    models = _load_models()
    return models.get(model_name)


def get_context_window(model_name: str, default: int = 32000) -> int:
    info = get_model_info(model_name)
    if info and info.get("context_window"):
        return int(info["context_window"])
    return default


def calculate_cost(model_name: str, usage: Usage) -> float | None:
    info = get_model_info(model_name)
    if not info:
        return None

    price_in = info.get("price_in")
    price_out = info.get("price_out")
    if price_in is None or price_out is None:
        return None

    price_cache_read = info.get("price_cache_read", price_in)
    price_cache_write = info.get("price_cache_write", price_in)

    cost = (
        (usage.input_tokens / 1_000_000.0) * price_in
        + (usage.output_tokens / 1_000_000.0) * price_out
        + (usage.cache_read_tokens / 1_000_000.0) * price_cache_read
        + (usage.cache_write_tokens / 1_000_000.0) * price_cache_write
    )
    return round(cost, 6)
