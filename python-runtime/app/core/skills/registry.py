"""Bounded, deterministic skill discovery for the Python runtime.

Skills are optional workspace files. Discovery is local and makes no model calls.
A skill is eligible only when its declared prerequisites are available.
"""
import os
import re
import shutil
from pathlib import Path

from app.core.skills.parser import load_skill_file
from app.core.skills.types import SkillManifest

MAX_SKILLS_TO_SCAN = 64
MAX_RUNBOOK_CHARS = 4_000


def _tokens(value: str) -> set[str]:
    return {word.lower() for word in re.findall(r"[a-zA-Z0-9_+-]{2,}", value)}


def _eligible(manifest: SkillManifest, available_tools: set[str]) -> bool:
    metadata = manifest.metadata
    if any(shutil.which(binary) is None for binary in metadata.requires_bins):
        return False
    if any(not os.environ.get(name) for name in metadata.requires_env):
        return False
    declared_tools = {name.strip() for name in metadata.tools if name.strip()}
    return not declared_tools or declared_tools.issubset(available_tools)


def select_skill(
    workspace_root: str | Path,
    task: str,
    available_tools: set[str],
) -> SkillManifest | None:
    """Select the best matching eligible SKILL.md without an LLM call.

    Search is intentionally limited to workspace-local skill directories. A skill
    is injected only when its name/description shares meaningful terms with the task.
    """
    root = Path(workspace_root)
    candidates: list[Path] = []
    for directory in (root / ".agentforge" / "skills", root / "skills"):
        if directory.is_dir():
            candidates.extend(sorted(directory.glob("**/SKILL.md")))
            if len(candidates) >= MAX_SKILLS_TO_SCAN:
                break

    scored: list[tuple[int, str, SkillManifest]] = []
    task_terms = _tokens(task)
    for path in candidates[:MAX_SKILLS_TO_SCAN]:
        try:
            manifest = load_skill_file(path)
        except Exception:
            # A malformed optional skill must never break an otherwise valid run.
            continue
        if not _eligible(manifest, available_tools):
            continue
        skill_terms = _tokens(f"{manifest.name} {manifest.description}")
        score = len(task_terms & skill_terms)
        if score:
            manifest.runbook_markdown = manifest.runbook_markdown[:MAX_RUNBOOK_CHARS]
            scored.append((score, manifest.name.casefold(), manifest))

    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored[0][2]
