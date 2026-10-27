"""Download and verify the default local embedding model for packaging."""
from __future__ import annotations

import os
from pathlib import Path

from fastembed import TextEmbedding

MODEL_NAME = "BAAI/bge-small-en-v1.5"
CACHE_DIR = Path(__file__).resolve().parents[1] / "models" / "embedding-cache"


def main() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    os.environ["FASTEMBED_CACHE_PATH"] = str(CACHE_DIR)
    model = TextEmbedding(model_name=MODEL_NAME, cache_dir=str(CACHE_DIR))
    vector = next(model.embed(["AgentForge local embedding verification"]))
    if not vector or not all(isinstance(value, (int, float)) for value in vector):
        raise RuntimeError("Embedding model verification returned an invalid vector")
    print(f"[embeddings] Verified {MODEL_NAME}; dimensions={len(vector)}; cache={CACHE_DIR}")


if __name__ == "__main__":
    main()
