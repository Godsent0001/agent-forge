"""Local embedding provider with bounded in-process result caching.

The model files are prepared by scripts/prepare_embedding_model.py during the
desktop packaging build. Runtime retrieval gracefully falls back to lexical
search when the model is unavailable.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

DEFAULT_EMBEDDING_MODEL = "local:BAAI/bge-small-en-v1.5"


def _model_cache_dir() -> Path:
    configured = os.environ.get("AGENTFORGE_EMBEDDING_CACHE_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "models" / "embedding-cache"


@lru_cache(maxsize=2)
def _load_model(model_id: str):
    if not model_id.startswith("local:"):
        raise ValueError(f"Unsupported embedding provider: {model_id.split(':', 1)[0]}")
    model_name = model_id.split(":", 1)[1]
    cache_dir = _model_cache_dir()
    if not cache_dir.is_dir() or not any(cache_dir.iterdir()):
        raise RuntimeError(
            "Local embedding model is not prepared. Rebuild AgentForge or prepare the model cache."
        )
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=model_name, cache_dir=str(cache_dir))


@lru_cache(maxsize=2048)
def _embed_cached(model_id: str, text: str) -> tuple[float, ...]:
    if model_id.startswith("local:"):
        model = _load_model(model_id)
        vector = next(model.embed([text]))
    elif model_id.startswith("venice/"):
        import httpx

        api_key = os.environ.get("VENICE_API_KEY")
        if not api_key:
            raise RuntimeError("Venice embeddings require VENICE_API_KEY in Provider settings.")
        model_name = model_id.split("/", 1)[1]
        endpoint = os.environ.get("VENICE_API_BASE", "https://api.venice.ai/api/v1").rstrip("/")
        with httpx.Client(timeout=30.0, trust_env=False) as client:
            response = client.post(
                f"{endpoint}/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model_name, "input": [text]},
            )
            response.raise_for_status()
            vector = response.json()["data"][0]["embedding"]
    else:
        # LiteLLM routes other provider/model embedding calls using the same
        # credentials already configured for chat completions.
        import litellm

        response = litellm.embedding(model=model_id, input=[text])
        vector = response.data[0]["embedding"]
    return tuple(float(value) for value in vector)


def embed_text(text: str, model_id: str = DEFAULT_EMBEDDING_MODEL) -> list[float]:
    """Embed one text value locally; results are cached by model and exact text."""
    if not text.strip():
        return []
    return list(_embed_cached(model_id, text))


def embed_many(texts: list[str], model_id: str = DEFAULT_EMBEDDING_MODEL) -> list[list[float]]:
    """Embed multiple texts, reusing cached vectors for repeated values."""
    if not texts:
        return []
    return [embed_text(value, model_id) for value in texts]


def cache_info() -> dict[str, int]:
    info = _embed_cached.cache_info()
    return {"hits": info.hits, "misses": info.misses, "size": info.currsize, "max_size": info.maxsize}


def clear_embedding_cache() -> None:
    _embed_cached.cache_clear()
    _load_model.cache_clear()
