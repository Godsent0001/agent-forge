"""C-4: the agent graph as the core sees it. Pure data (see docs/CONTRACTS.md)."""
from typing import Literal

from pydantic import BaseModel


class LLMParams(BaseModel):
    temperature: float | None = 0.2
    max_tokens: int | None = None
    timeout_s: int = 60
    reasoning: Literal["off", "low", "medium", "high"] = "off"   # thinking effort, if the model supports it


class ToolBinding(BaseModel):
    id: str                      # tools.id (the row)
    kind: str                    # "web_search", "python", ...
    name: str                    # name shown to the model; sanitized and unique within the agent
    description: str | None = None   # overrides Tool.default_description when set
    config: dict = {}


class ChildLink(BaseModel):
    agent_id: str
    description: str | None = None


class AgentSpec(BaseModel):
    id: str
    name: str
    description: str = ""
    provider: str
    model: str
    system_prompt: str = ""
    tool_guidance: str = ""      # DB column is still `tool_use_schema`; the loader maps it
    memory_enabled: bool = False
    lessons_enabled: bool = False
    params: LLMParams = LLMParams()
    tools: list[ToolBinding] = []
    children: list[ChildLink] = []


class AgentGraph(BaseModel):
    root_id: str
    agents: dict[str, AgentSpec]
