from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.contracts.graph import AgentGraph, AgentSpec, ChildLink, ToolBinding
from app.contracts.naming import dedupe_names


def load_agent_graph(db: Session, project_id: str, root_agent_id: str) -> AgentGraph:
    root = db.execute(
        select(models.Agent)
        .where(models.Agent.id == root_agent_id, models.Agent.project_id == project_id)
        .options(
            selectinload(models.Agent.tool_links).selectinload(models.AgentToolLink.tool),
            selectinload(models.Agent.child_links),
        )
    ).scalar_one_or_none()
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
        child_links = list(row.child_links)
        raw_names = [link.tool.name for link in tool_rows]
        tool_names = dedupe_names(raw_names)

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
        for link in child_links:
            child = db.get(models.Agent, link.child_agent_id)
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
