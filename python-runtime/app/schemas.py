"""
Pydantic schemas — the validated boundary between the API and the DB.
Per the spec: AgentConfig, ToolDefinition, ExecutionEvent-shaped objects
all get strong schemas here so the system doesn't become a mess as it grows.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str
    parallel_execution: bool = False


class ProjectUpdate(BaseModel):
    name: str | None = None
    parallel_execution: bool | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    parallel_execution: bool
    created_at: datetime


class ToolCreate(BaseModel):
    project_id: str
    name: str
    description: str = ""
    kind: str
    input_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)
    config: dict = Field(default_factory=dict)


class ToolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    name: str
    description: str
    kind: str
    input_schema: dict
    output_schema: dict
    config: dict


class AgentCreate(BaseModel):
    project_id: str
    name: str
    description: str = ""
    provider: str = "anthropic"
    model: str = ""
    system_prompt: str = ""
    tool_use_schema: str = ""
    memory_enabled: bool = False
    learned_experience: str = ""


class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    provider: str | None = None
    model: str | None = None
    system_prompt: str | None = None
    tool_use_schema: str | None = None
    memory_enabled: bool | None = None
    learned_experience: str | None = None


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    name: str
    description: str
    provider: str
    model: str
    system_prompt: str
    tool_use_schema: str
    memory_enabled: bool
    learned_experience: str
    created_at: datetime
    tool_ids: list[str] = Field(default_factory=list)
    child_agent_ids: list[str] = Field(default_factory=list)


class AttachToolRequest(BaseModel):
    agent_id: str
    tool_id: str


class DetachToolRequest(BaseModel):
    agent_id: str
    tool_id: str


class AttachChildAgentRequest(BaseModel):
    parent_agent_id: str
    child_agent_id: str
    description: str = ""


class DetachChildAgentRequest(BaseModel):
    parent_agent_id: str
    child_agent_id: str


class ExecutionEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    type: str
    agent_name: str | None
    tool_name: str | None
    depth: int
    data: dict
    timestamp: datetime


class ExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    root_agent_id: str
    input_task: str
    final_output: str
    status: str
    started_at: datetime
    completed_at: datetime | None
