from app.services.graph_loader import _assigned_skills, _with_assigned_skills


def test_assigned_skill_catalogue_is_added_to_agent_prompt():
    skills = _assigned_skills("agent-1", [{
        "id": "skill-1",
        "name": "Research carefully",
        "description": "Verify claims against sources.",
        "instructions": "Long instructions are loaded on demand.",
        "assigned_agent_ids": ["agent-1"],
        "enabled": True,
    }])
    result = _with_assigned_skills("Base prompt", skills)

    assert result.startswith("Base prompt")
    assert "[Assigned project skills]" in result
    assert "Research carefully" in result
    assert "Verify claims against sources." in result
    assert "Long instructions are loaded on demand." not in result
    assert "load_skill" in result


def test_unassigned_or_disabled_skills_are_not_added():
    skills = _assigned_skills("agent-1", [
        {"id": "skill-2", "name": "Other agent", "instructions": "other", "assigned_agent_ids": ["agent-2"]},
        {"id": "skill-3", "name": "Disabled", "instructions": "disabled", "assigned_agent_ids": ["agent-1"], "enabled": False},
    ])
    assert _with_assigned_skills("Base prompt", skills) == "Base prompt"


def test_skill_catalogue_is_bounded_and_limited_to_ten_skills():
    skills = _assigned_skills("agent-1", [
        {
            "id": f"skill-{index}",
            "name": f"Skill {index}",
            "description": "x" * 3000,
            "instructions": "y" * 3000,
            "assigned_agent_ids": ["agent-1"],
            "enabled": True,
        }
        for index in range(20)
    ])
    result = _with_assigned_skills("Base prompt", skills)

    assert len(skills) == 10
    assert result.count("skill-") <= 10
    assert len(result) < 7000
