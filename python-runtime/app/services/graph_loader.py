from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.contracts.graph import AgentGraph, AgentSpec, ChildLink, ToolBinding
from app.contracts.naming import dedupe_names


def load_agent_graph(db: Session, project_id: str, root_agent_id: str) -> AgentGraph:
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
        tool_names = dedupe_names([link.tool.name for link in tool_rows])
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
            system_prompt=row.system_prompt,
            tool_guidance=row.tool_use_schema,
            memory_enabled=row.memory_enabled,
            lessons_enabled=row.lessons_enabled,
            params=row.params or {},
            tools=bindings,
            children=children,
        )

    return AgentGraph(root_id=root.id, agents=agents)
