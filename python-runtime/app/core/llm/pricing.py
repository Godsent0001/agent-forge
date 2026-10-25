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


def _litellm_info(model_name: str) -> dict[str, Any] | None:
    """Fallback to LiteLLM's bundled price table, normalized to our per-million fields."""
    try:
        import litellm
    except ImportError:  # pragma: no cover - hard dependency
        return None
    table = getattr(litellm, "model_cost", None) or {}
    entry = table.get(model_name)
    if entry is None and "/" in model_name:
        entry = table.get(model_name.split("/", 1)[1])
    if not isinstance(entry, dict):
        return None
    per_token_in = entry.get("input_cost_per_token")
    per_token_out = entry.get("output_cost_per_token")
    if per_token_in is None or per_token_out is None:
        return None
    info: dict[str, Any] = {
        "model": model_name,
        "price_in": float(per_token_in) * 1_000_000,
        "price_out": float(per_token_out) * 1_000_000,
    }
    if entry.get("cache_read_input_token_cost") is not None:
        info["price_cache_read"] = float(entry["cache_read_input_token_cost"]) * 1_000_000
    if entry.get("cache_creation_input_token_cost") is not None:
        info["price_cache_write"] = float(entry["cache_creation_input_token_cost"]) * 1_000_000
    if entry.get("max_input_tokens"):
        info["context_window"] = int(entry["max_input_tokens"])
    return info


def get_model_info(model_name: str) -> dict[str, Any] | None:
    models = _load_models()
    return models.get(model_name) or _litellm_info(model_name)


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

    # Provider usage (OpenAI-style, as LiteLLM reports it) counts cached prompt tokens
    # inside input_tokens; bill them once, at the cache rate.
    cached = min(usage.cache_read_tokens + usage.cache_write_tokens, usage.input_tokens)
    uncached_input = usage.input_tokens - cached
    cost = (
        (uncached_input / 1_000_000.0) * price_in
        + (usage.output_tokens / 1_000_000.0) * price_out
        + (usage.cache_read_tokens / 1_000_000.0) * price_cache_read
        + (usage.cache_write_tokens / 1_000_000.0) * price_cache_write
    )
    return round(cost, 6)
