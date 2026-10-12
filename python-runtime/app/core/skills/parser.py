"""Parser for SKILL.md files containing YAML frontmatter and operational runbooks."""
from pathlib import Path
import yaml
from .types import SkillManifest, SkillMetadata


def parse_skill_markdown(content: str) -> SkillManifest:
    """Parse SKILL.md markdown text containing YAML frontmatter delimited by '---'."""
    text = content.strip()
    if not text.startswith("---"):
        return SkillManifest(name="default_skill", runbook_markdown=text)

    parts = text.split("---", 2)
    if len(parts) < 3:
        return SkillManifest(name="default_skill", runbook_markdown=text)

    frontmatter_raw = parts[1].strip()
    runbook_raw = parts[2].strip()

    data = yaml.safe_load(frontmatter_raw) or {}
    meta_dict = data.get("metadata", {})

    metadata = SkillMetadata(
        requires_bins=meta_dict.get("requires_bins", []),
        requires_env=meta_dict.get("requires_env", []),
        tools=data.get("tools", meta_dict.get("tools", [])),
    )

    return SkillManifest(
        name=data.get("name", "skill"),
        description=data.get("description", ""),
        metadata=metadata,
        runbook_markdown=runbook_raw,
    )


def load_skill_file(filepath: str | Path) -> SkillManifest:
    p = Path(filepath)
    if not p.is_file():
        raise FileNotFoundError(f"Skill file '{filepath}' not found.")
    content = p.read_text(encoding="utf-8", errors="replace")
    return parse_skill_markdown(content)
