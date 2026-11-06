from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.tools.workspace_capabilities import ProjectSkillTool
from app.services.graph_loader import _assigned_skills, _with_assigned_skills


def _skills():
    return [
        {
            "id": "skill-code-review",
            "name": "Code Review",
            "description": "Review code for correctness and regressions.",
            "instructions": "Inspect changed paths, run targeted tests, and report evidence.",
            "assigned_agent_ids": ["agent-1"],
            "enabled": True,
        },
        {
            "id": "skill-disabled",
            "name": "Disabled",
            "description": "Not available.",
            "instructions": "Do not load me.",
            "assigned_agent_ids": ["agent-1"],
            "enabled": False,
        },
    ]


def test_assigned_skill_catalog_is_compact_and_scoped_to_agent():
    skills = _assigned_skills("agent-1", _skills())
    assert [skill["id"] for skill in skills] == ["skill-code-review"]
    prompt = _with_assigned_skills("Base prompt", skills)
    assert "Code Review" in prompt
    assert "Review code for correctness" in prompt
    assert "Inspect changed paths" not in prompt
    assert "skill-disabled" not in prompt
    assert _assigned_skills("agent-2", _skills()) == []


@pytest.mark.asyncio
async def test_skill_tool_loads_full_instructions_only_for_requested_skill():
    skills = _assigned_skills("agent-1", _skills())
    tool = ProjectSkillTool(skills)
    result = await tool.run(
        tool.Input(skill_id="skill-code-review"),
        SimpleNamespace(project_id="project-1", agent_id="agent-1"),
    )
    assert result.ok
    assert "Inspect changed paths, run targeted tests" in result.content
    assert "cannot override safety requirements" in result.content.lower()
