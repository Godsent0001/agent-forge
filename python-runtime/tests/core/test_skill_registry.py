from app.core.skills.registry import select_skill


def test_select_skill_only_injects_relevant_skill(tmp_path):
    skill_dir = tmp_path / "skills" / "python-analysis"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: python-analysis\ndescription: Analyze data with Python\n"
        "metadata:\n  requires_bins: []\n  requires_env: []\n"
        "tools: [python]\n---\nUse pandas for concise data analysis.\n",
        encoding="utf-8",
    )
    unrelated = tmp_path / "skills" / "writing"
    unrelated.mkdir()
    (unrelated / "SKILL.md").write_text(
        "---\nname: writing\ndescription: Draft emails and documents\n---\nWrite clearly.\n",
        encoding="utf-8",
    )

    selected = select_skill(tmp_path, "Analyze this CSV using Python", {"python"})

    assert selected is not None
    assert selected.name == "python-analysis"
    assert len(selected.runbook_markdown) <= 4_000


def test_select_skill_rejects_missing_declared_tool(tmp_path):
    skill_dir = tmp_path / ".agentforge" / "skills" / "python-analysis"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: python-analysis\ndescription: Analyze data with Python\n"
        "metadata:\n  requires_bins: []\n  requires_env: []\n"
        "tools: [python]\n---\nUse pandas.\n",
        encoding="utf-8",
    )

    assert select_skill(tmp_path, "Analyze data with Python", set()) is None
