"""Workspace artifact lifecycle and cleanup utilities."""
import time
from pathlib import Path


def cleanup_ephemeral_artifacts(workspace_root: Path, max_age_seconds: int = 86400) -> int:
    """Clean up old temporary result files in .results/ older than max_age_seconds.

    A zero or negative age is an explicit request to remove every matching
    ephemeral result, regardless of small filesystem timestamp-resolution
    differences that can make a newly-created file appear slightly in the future.
    """
    results_dir = workspace_root / ".results"
    if not results_dir.is_dir():
        return 0

    now = time.time()
    delete_all = max_age_seconds <= 0
    deleted_count = 0

    for file_path in results_dir.glob("*.txt"):
        try:
            mtime = file_path.stat().st_mtime
            if delete_all or now - mtime >= max_age_seconds:
                file_path.unlink()
                deleted_count += 1
        except (OSError, PermissionError):
            continue

    return deleted_count
