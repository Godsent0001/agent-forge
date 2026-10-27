"""Small bounded TTL cache for eligible LLM completions."""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
from typing import Any

CACHE_TTL_SECONDS = 120
CACHE_MAX_ENTRIES = 256
_lock = threading.Lock()
_cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()


def cache_enabled() -> bool:
    return os.environ.get("AGENTFORGE_LLM_CACHE", "1").strip().lower() not in {"0", "false", "off"}


def make_cache_key(*, model: str, messages: list[dict], temperature: float | None, max_tokens: int | None) -> str:
    payload = json.dumps(
        {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_cached(key: str, *, now: float | None = None):
    current = time.monotonic() if now is None else now
    with _lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at <= current:
            _cache.pop(key, None)
            return None
        _cache.move_to_end(key)
        return value


def set_cached(key: str, value: Any, *, now: float | None = None) -> None:
    current = time.monotonic() if now is None else now
    with _lock:
        _cache[key] = (current + CACHE_TTL_SECONDS, value)
        _cache.move_to_end(key)
        while len(_cache) > CACHE_MAX_ENTRIES:
            _cache.popitem(last=False)


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def cache_stats() -> dict[str, int]:
    current = time.monotonic()
    with _lock:
        expired = [key for key, (expiry, _) in _cache.items() if expiry <= current]
        for key in expired:
            _cache.pop(key, None)
        return {"entries": len(_cache), "max_entries": CACHE_MAX_ENTRIES}
