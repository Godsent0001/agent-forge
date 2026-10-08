"""Skill manifest types for AgentForge Core."""
from pydantic import BaseModel, Field


class SkillMetadata(BaseModel):
    requires_bins: list[str] = Field(default_factory=list)
    requires_env: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)


class SkillManifest(BaseModel):
    name: str
    description: str = ""
    metadata: SkillMetadata = Field(default_factory=SkillMetadata)
    runbook_markdown: str = ""
