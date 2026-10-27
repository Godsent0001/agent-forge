"""Download, normalize, and verify the default local embedding model for packaging."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from fastembed import TextEmbedding

MODEL_NAME = "BAAI/bge-small-en-v1.5"
CACHE_DIR = Path(__file__).resolve().parents[1] / "models" / "embedding-cache"


def _materialize_symlinks(root: Path) -> int:
    """Replace Hugging Face cache symlinks with regular files/directories.

    The snapshot files downloaded by fastembed can be symlinks into the cache's
    blobs directory. electron-builder's Windows 7-Zip packager treats those
    reparse points as invalid file/directory entries. Materializing links keeps
    the same cache layout while making the staged model portable in installers.
    """
    entries: list[Path] = []
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        entries.extend(Path(current) / name for name in directories)
        entries.extend(Path(current) / name for name in files)

    replaced = 0
    for path in sorted(entries, key=lambda item: len(item.parts), reverse=True):
        if not path.is_symlink():
            continue
        target = path.resolve(strict=True)
        path.unlink()
        if target.is_dir():
            shutil.copytree(target, path, symlinks=False)
        else:
            shutil.copy2(target, path)
        replaced += 1
    return replaced


def main() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    os.environ["FASTEMBED_CACHE_PATH"] = str(CACHE_DIR)

    model = TextEmbedding(model_name=MODEL_NAME, cache_dir=str(CACHE_DIR))
    vector = [float(value) for value in next(model.embed(["AgentForge local embedding verification"]))]
    if not vector or not all(isinstance(value, float) for value in vector):
        raise RuntimeError("Embedding model verification returned an invalid vector")

    links = _materialize_symlinks(CACHE_DIR)
    # Load from the normalized on-disk cache, not the model instance used before
    # normalization, so the packaged files are verified in their final form.
    model = TextEmbedding(model_name=MODEL_NAME, cache_dir=str(CACHE_DIR))
    normalized_vector = [float(value) for value in next(model.embed(["AgentForge packaged embedding verification"]))]
    if len(normalized_vector) != len(vector):
        raise RuntimeError("Normalized embedding cache returned an unexpected vector size")

    print(
        f"[embeddings] Verified {MODEL_NAME}; dimensions={len(normalized_vector)}; "
        f"materialized_links={links}; cache={CACHE_DIR}"
    )


if __name__ == "__main__":
    main()
