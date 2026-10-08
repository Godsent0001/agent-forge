"""Workspace artifact lifecycle and cleanup utilities."""
import time
from pathlib import Path


def cleanup_ephemeral_artifacts(workspace_root: Path, max_age_seconds: int = 86400) -> int:
    """Clean up old temporary result files in .results/ older than max_age_seconds."""
    results_dir = workspace_root / ".results"
    if not results_dir.is_dir():
        return 0

    now = time.time()
    deleted_count = 0

    for file_path in results_dir.glob("*.txt"):
        try:
            mtime = file_path.stat().st_mtime
            if now - mtime > max_age_seconds:
                file_path.unlink()
                deleted_count += 1
        except Exception:
            continue

    return deleted_count
