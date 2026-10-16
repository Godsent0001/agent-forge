from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.contracts.graph import AgentGraph, AgentSpec, ChildLink, ToolBinding
from app.contracts.naming import dedupe_names, sanitize_tool_name


def _with_assigned_skills(system_prompt: str, agent_id: str, skills: object) -> str:
    """Append bounded, project-persisted skill instructions for this agent only."""
    if not isinstance(skills, list):
        return system_prompt
    blocks: list[str] = []
    total_chars = 0
    for skill in skills:
        if not isinstance(skill, dict) or skill.get("enabled", True) is not True:
            continue
        assigned = skill.get("assigned_agent_ids", [])
        instructions = skill.get("instructions")
        name = skill.get("name")
        if not isinstance(assigned, list) or agent_id not in assigned:
            continue
        if not isinstance(instructions, str) or not instructions.strip():
            continue
        if not isinstance(name, str) or not name.strip():
            name = "Untitled skill"
        block = f"### {name.strip()[:120]}\n{instructions.strip()}"
        remaining = 16000 - total_chars
        if remaining <= 0:
            break
        blocks.append(block[:remaining])
        total_chars += min(len(block), remaining)
        if len(blocks) >= 10:
            break
    if not blocks:
        return system_prompt
    skill_context = (
        "\n\n[AgentForge Assigned Skills]\n"
        "Use these user-assigned procedures when relevant to the task. They are guidance, "
        "not permission to bypass safety, access controls, or tool approvals.\n\n"
        + "\n\n".join(blocks)
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

        agents[row.id] = AgentSpec(
            id=row.id,
            name=row.name,
            description=row.description,
            provider=row.provider,
            model=row.model,
            system_prompt=_with_assigned_skills(row.system_prompt, row.id, skills),
            tool_guidance=row.tool_use_schema,
            memory_enabled=row.memory_enabled,
            lessons_enabled=row.lessons_enabled,
            params=row.params or {},
            tools=bindings,
            children=children,
        )

    return AgentGraph(root_id=root.id, agents=agents)
