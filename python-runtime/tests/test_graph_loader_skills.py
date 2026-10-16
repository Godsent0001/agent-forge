from app.services.graph_loader import _with_assigned_skills


def test_assigned_skill_instructions_are_added_to_agent_prompt():
    result = _with_assigned_skills(
        "Base prompt",
        "agent-1",
        [{
            "id": "skill-1",
            "name": "Research carefully",
            "instructions": "Verify claims against sources.",
            "assigned_agent_ids": ["agent-1"],
            "enabled": True,
        }],
    )

    assert result.startswith("Base prompt")
    assert "[AgentForge Assigned Skills]" in result
    assert "### Research carefully" in result
    assert "Verify claims against sources." in result


def test_unassigned_or_disabled_skills_are_not_added():
    result = _with_assigned_skills(
        "Base prompt",
        "agent-1",
        [
            {"name": "Other agent", "instructions": "other", "assigned_agent_ids": ["agent-2"]},
            {"name": "Disabled", "instructions": "disabled", "assigned_agent_ids": ["agent-1"], "enabled": False},
        ],
    )

    assert result == "Base prompt"


def test_skill_context_is_bounded_and_limited_to_ten_skills():
    skills = [
        {
            "name": f"Skill {index}",
            "instructions": "x" * 3000,
            "assigned_agent_ids": ["agent-1"],
            "enabled": True,
        }
        for index in range(20)
    ]

    result = _with_assigned_skills("Base prompt", "agent-1", skills)

    assert result.count("### Skill ") <= 10
    assert len(result) < 17000
