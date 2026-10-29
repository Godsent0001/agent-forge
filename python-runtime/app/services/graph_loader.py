from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.contracts.graph import AgentGraph, AgentSpec, ChildLink, ToolBinding
from app.contracts.naming import dedupe_names, sanitize_tool_name


def _assigned_skills(agent_id: str, skills: object) -> list[dict]:
    """Return bounded skill records assigned to one agent."""
    if not isinstance(skills, list):
        return []
    assigned_skills: list[dict] = []
    for skill in skills:
        if not isinstance(skill, dict) or skill.get("enabled", True) is not True:
            continue
        assigned = skill.get("assigned_agent_ids", [])
        skill_id = skill.get("id")
        instructions = skill.get("instructions")
        if not isinstance(assigned, list) or agent_id not in assigned:
            continue
        if not isinstance(skill_id, str) or not skill_id.strip():
            continue
        if not isinstance(instructions, str) or not instructions.strip():
            continue
        assigned_skills.append({
            "id": skill_id[:200],
            "name": str(skill.get("name") or "Untitled skill")[:120],
            "description": str(skill.get("description") or "")[:500],
            "instructions": instructions.strip()[:16000],
        })
        if len(assigned_skills) >= 10:
            break
    return assigned_skills


def _with_assigned_skills(system_prompt: str, skills: list[dict]) -> str:
    """Add only a compact skill index; full procedures are loaded by the skill tool."""
    if not skills:
        return system_prompt
    lines = [
        f"- id={skill['id']!r} | {skill['name']}: {skill['description'] or 'No description provided.'}"
        for skill in skills
    ]
    skill_context = (
        "\n\n[Assigned project skills]\n"
        "These are compact descriptions of user-assigned procedures. When a skill is relevant, "
        "call load_skill with its exact ID to read the full instructions. Do not load unrelated skills.\n"
        + "\n".join(lines)
    )
    return (system_prompt or "").rstrip() + skill_context


def load_agent_graph(db: Session, project_id: str, root_agent_id: str) -> AgentGraph:
    project = db.get(models.Project, project_id)
    project_settings = project.settings if project is not None and isinstance(project.settings, dict) else {}
    skills = project_settings.get("skills", [])
    rows = db.execute(
        select(models.Agent)
        .where(models.Agent.project_id == project_id)
        .options(
            selectinload(models.Agent.tool_links).selectinload(models.AgentToolLink.tool),
            selectinload(models.Agent.child_links),
        )
    ).scalars().all()
    by_id = {row.id: row for row in rows}
    root = by_id.get(root_agent_id)
    if root is None:
        raise ValueError("Root agent not found in project")

    agents: dict[str, AgentSpec] = {}
    pending = [root]
    seen: set[str] = set()

    while pending:
        row = pending.pop()
        if row.id in seen:
            continue
        seen.add(row.id)

        tool_rows = list(row.tool_links)
        tool_names = dedupe_names([sanitize_tool_name(link.tool.name) for link in tool_rows])
        bindings = [
            ToolBinding(
                id=link.tool.id,
                kind=link.tool.kind,
                name=name,
                description=link.tool.description or None,
                config=link.tool.config or {},
            )
            for link, name in zip(tool_rows, tool_names)
        ]

        children: list[ChildLink] = []
        for link in row.child_links:
            child = by_id.get(link.child_agent_id)
            if child is None:
                continue
            children.append(ChildLink(agent_id=child.id, description=link.description or None))
            pending.append(child)

        assigned_skills = _assigned_skills(row.id, skills)
        if assigned_skills:
            bindings.append(ToolBinding(
                id=f"project-skill:{row.id}",
                kind="project_skill",
                name="load_skill",
                description="Load full instructions for one relevant assigned skill by its ID.",
                config={"skills": assigned_skills},
            ))

        agents[row.id] = AgentSpec(
            id=row.id,
            name=row.name,
            description=row.description,
            provider=row.provider,
            model=row.model,
            system_prompt=_with_assigned_skills(row.system_prompt, assigned_skills),
            tool_guidance=row.tool_use_schema,
            memory_enabled=row.memory_enabled,
            lessons_enabled=row.lessons_enabled,
            params=row.params or {},
            tools=bindings,
            children=children,
        )

    return AgentGraph(root_id=root.id, agents=agents)
