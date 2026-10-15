"""Project-scoped management actions for the floating System Engineer.

This tool deliberately exposes a small, non-destructive set of operations:
inspect project state, create/update agents, create public HTTP tools, connect
agents/tools into workflows, manage skills, and verify execution outcomes.
It never deletes resources or accesses another project.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import ClassVar, Literal

from pydantic import BaseModel, Field
from app import models
from app.contracts.tools import Tool, ToolContext, ToolResult
from app.db import SessionLocal
from app.graph import GraphValidationError, validate_new_link


class AgentForgeControlInput(BaseModel):
    operation: Literal[
        "inspect_project",
        "create_agent",
        "update_agent",
        "create_custom_http_tool",
        "attach_tool",
        "attach_child_agent",
        "save_skill",
        "verify_execution",
    ] = Field(description="The project-management operation to perform.")
    agent_id: str | None = Field(default=None, description="Existing agent ID for update/attachment.")
    name: str | None = Field(default=None, description="Agent, tool, or skill name.")
    description: str | None = Field(default=None, description="Description for the new or updated resource.")
    system_prompt: str | None = Field(default=None, description="Full system prompt for a new or updated agent.")
    provider: str | None = Field(default=None, description="Model provider for an agent, such as anthropic or openai.")
    model: str | None = Field(default=None, description="Model identifier for an agent.")
    tool_id: str | None = Field(default=None, description="Existing tool ID to attach to an agent.")
    child_agent_id: str | None = Field(default=None, description="Existing child agent ID to connect to a parent agent.")
    endpoint_url: str | None = Field(default=None, description="Public HTTP(S) endpoint for a custom tool.")
    http_method: Literal["GET", "POST"] | None = Field(default="POST", description="HTTP method for a custom tool.")
    input_schema: dict | None = Field(default=None, description="JSON Schema object describing custom-tool arguments.")
    skill_id: str | None = Field(default=None, description="Existing skill ID to update; omit to create a skill.")
    skill_instructions: str | None = Field(default=None, description="Reusable procedure/instructions for a skill.")
    assigned_agent_ids: list[str] | None = Field(default=None, description="Agent IDs that should receive this skill.")
    execution_id: str | None = Field(default=None, description="Execution ID to inspect and verify.")
    memory_enabled: bool | None = Field(default=None, description="Whether agent memory is enabled.")
    lessons_enabled: bool | None = Field(default=None, description="Whether agent lessons are enabled.")
    params: dict | None = Field(default=None, description="Agent runtime parameters.")


class AgentForgeControlTool(Tool):
    """Safe, project-scoped mutations for the System Engineer agent."""

    kind: ClassVar[str] = "agentforge_control"
    default_description: ClassVar[str] = (
        "Inspect and manage AgentForge resources in the current project. Use this tool "
        "to create/update agents, configure public HTTP tools, connect agents/tools into "
        "workflows, manage skills, and verify execution outcomes. Never claim a change "
        "succeeded until the tool result confirms it."
    )
    Input: ClassVar[type[BaseModel]] = AgentForgeControlInput
    permissions: ClassVar[set] = set()

    async def run(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        values = args.model_dump(exclude_none=True)
        operation = values["operation"]
        result: dict
        with SessionLocal() as db:
            project = db.get(models.Project, ctx.project_id)
            if project is None:
                return ToolResult(ok=False, content="Current project was not found.")

            if operation == "inspect_project":
                agents = db.query(models.Agent).filter_by(project_id=project.id).all()
                tools = db.query(models.Tool).filter_by(project_id=project.id).all()
                executions = (
                    db.query(models.Execution)
                    .filter_by(project_id=project.id)
                    .order_by(models.Execution.started_at.desc())
                    .limit(10)
                    .all()
                )
                settings = project.settings if isinstance(project.settings, dict) else {}
                result = {
                    "project": {"id": project.id, "name": project.name},
                    "agents": [
                        {"id": a.id, "name": a.name, "description": a.description,
                         "provider": a.provider, "model": a.model,
                         "tool_ids": [link.tool_id for link in a.tool_links],
                         "child_agent_ids": [link.child_agent_id for link in a.child_links]}
                        for a in agents
                    ],
                    "tools": [
                        {"id": t.id, "name": t.name, "kind": t.kind, "description": t.description}
                        for t in tools
                    ],
                    "skills": [
                        {"id": s.get("id"), "name": s.get("name"),
                         "assigned_agent_ids": s.get("assigned_agent_ids", []),
                         "enabled": s.get("enabled", True)}
                        for s in settings.get("skills", []) if isinstance(s, dict)
                    ],
                    "recent_executions": [
                        {"id": e.id, "root_agent_id": e.root_agent_id, "status": e.status,
                         "task": (e.input_task or "")[:300], "error": (e.error or "")[:1200],
                         "output_preview": (e.final_output or "")[:800]}
                        for e in executions
                    ],
                }
            elif operation == "create_agent":
                name = str(values.get("name", "")).strip()
                if not name:
                    return ToolResult(ok=False, content="create_agent requires a non-empty name.")
                agent = models.Agent(
                    project_id=project.id,
                    name=name[:160],
                    description=str(values.get("description", ""))[:2000],
                    provider=str(values.get("provider", "anthropic")),
                    model=str(values.get("model", "")),
                    system_prompt=str(values.get("system_prompt", "")),
                    memory_enabled=bool(values.get("memory_enabled", False)),
                    lessons_enabled=bool(values.get("lessons_enabled", False)),
                    params=values.get("params", {}),
                )
                db.add(agent)
                db.commit()
                db.refresh(agent)
                result = {"created": True, "agent_id": agent.id, "name": agent.name}
            elif operation == "update_agent":
                agent = self._agent_in_project(db, project.id, values.get("agent_id"))
                if agent is None:
                    return ToolResult(ok=False, content="update_agent requires an agent_id belonging to the current project.")
                allowed = ("name", "description", "provider", "model", "system_prompt",
                           "memory_enabled", "lessons_enabled", "params")
                for field in allowed:
                    if field in values:
                        value = values[field]
                        if field == "name":
                            value = str(value).strip()[:160]
                            if not value:
                                return ToolResult(ok=False, content="Agent name cannot be empty.")
                        elif field in {"description", "system_prompt"}:
                            value = str(value)[:20000 if field == "system_prompt" else 2000]
                        setattr(agent, field, value)
                db.commit()
                db.refresh(agent)
                result = {"updated": True, "agent_id": agent.id, "name": agent.name,
                          "provider": agent.provider, "model": agent.model}
            elif operation == "create_custom_http_tool":
                name = str(values.get("name", "")).strip()
                url = str(values.get("endpoint_url", "")).strip()
                method = values.get("http_method", "POST")
                schema = values.get("input_schema", {"type": "object", "properties": {}})
                if not name or not url.startswith(("https://", "http://")):
                    return ToolResult(ok=False, content="A tool name and absolute public HTTP(S) endpoint_url are required.")
                if not isinstance(schema, dict) or schema.get("type", "object") != "object":
                    return ToolResult(ok=False, content="input_schema must be a JSON Schema object.")
                tool = models.Tool(
                    project_id=project.id,
                    name=name[:120],
                    description=str(values.get("description", ""))[:2000],
                    kind="custom_http",
                    input_schema=schema,
                    config={"url": url, "method": method, "input_schema": schema},
                )
                db.add(tool)
                db.commit()
                db.refresh(tool)
                result = {"created": True, "tool_id": tool.id, "name": tool.name,
                          "kind": tool.kind, "note": "Attach it to an agent before use."}
            elif operation == "attach_tool":
                agent = self._agent_in_project(db, project.id, values.get("agent_id"))
                tool = db.get(models.Tool, values.get("tool_id", ""))
                if agent is None or tool is None or tool.project_id != project.id:
                    return ToolResult(ok=False, content="agent_id and tool_id must both belong to the current project.")
                existing = db.query(models.AgentToolLink).filter_by(agent_id=agent.id, tool_id=tool.id).first()
                if existing is None:
                    db.add(models.AgentToolLink(agent_id=agent.id, tool_id=tool.id))
                    db.commit()
                result = {"attached": True, "agent_id": agent.id, "tool_id": tool.id,
                          "agent_name": agent.name, "tool_name": tool.name}
            elif operation == "attach_child_agent":
                parent = self._agent_in_project(db, project.id, values.get("agent_id"))
                child = self._agent_in_project(db, project.id, values.get("child_agent_id"))
                if parent is None or child is None:
                    return ToolResult(ok=False, content="Both agent_id and child_agent_id must belong to the current project.")
                try:
                    validate_new_link(db, parent.id, child.id)
                except GraphValidationError as exc:
                    return ToolResult(ok=False, content=f"Workflow link rejected: {exc}")
                existing = db.query(models.AgentAgentLink).filter_by(
                    parent_agent_id=parent.id, child_agent_id=child.id
                ).first()
                if existing is None:
                    db.add(models.AgentAgentLink(
                        parent_agent_id=parent.id,
                        child_agent_id=child.id,
                        description=str(values.get("description", ""))[:1000],
                    ))
                    db.commit()
                result = {"attached": True, "parent_agent_id": parent.id,
                          "child_agent_id": child.id, "parent": parent.name, "child": child.name}
            elif operation == "save_skill":
                name = str(values.get("name", "")).strip()
                instructions = str(values.get("skill_instructions", "")).strip()
                if not name or not instructions:
                    return ToolResult(ok=False, content="save_skill requires a name and skill_instructions.")
                settings = dict(project.settings or {})
                skills = [item for item in settings.get("skills", []) if isinstance(item, dict)]
                skill_id = values.get("skill_id")
                skill = next((item for item in skills if item.get("id") == skill_id), None) if skill_id else None
                if skill is None:
                    skill_id = f"skill-{uuid.uuid4()}"
                    skill = {"id": skill_id, "created_at": __import__("datetime").datetime.now().astimezone().isoformat()}
                    skills.append(skill)
                assigned = values.get("assigned_agent_ids", [])
                valid_agents = {a.id for a in db.query(models.Agent.id).filter_by(project_id=project.id).all()}
                if not isinstance(assigned, list) or any(item not in valid_agents for item in assigned):
                    return ToolResult(ok=False, content="assigned_agent_ids may only contain agents in the current project.")
                skill.update({
                    "name": name[:120],
                    "description": str(values.get("description", ""))[:500],
                    "instructions": instructions[:16000],
                    "assigned_agent_ids": assigned,
                    "enabled": True,
                    "updated_at": __import__("datetime").datetime.now().astimezone().isoformat(),
                })
                settings["skills"] = skills
                project.settings = settings
                db.commit()
                result = {"saved": True, "skill_id": skill_id, "name": name, "assigned_agent_ids": assigned}
            elif operation == "verify_execution":
                execution = db.get(models.Execution, values.get("execution_id", ""))
                if execution is None or execution.project_id != project.id:
                    return ToolResult(ok=False, content="execution_id was not found in the current project.")
                result = {
                    "verified": execution.status in {"completed", "error", "cancelled", "budget_exceeded", "interrupted"},
                    "execution_id": execution.id,
                    "status": execution.status,
                    "error": execution.error,
                    "output_preview": (execution.final_output or "")[:2000],
                }
            else:
                return ToolResult(ok=False, content=f"Unsupported operation: {operation}")
        return ToolResult(content=json.dumps(result, ensure_ascii=False, default=str))

    @staticmethod
    def _agent_in_project(db: Session, project_id: str, agent_id: str | None):
        if not agent_id:
            return None
        return db.query(models.Agent).filter_by(id=agent_id, project_id=project_id).first()
