from pydantic import BaseModel, Field


class LLMParams(BaseModel):
    temperature: float | None = 0.2
    max_tokens: int | None = None
    timeout_s: int = 60


class ToolBinding(BaseModel):
    id: str
    kind: str
    name: str
    description: str | None = None
    config: dict = Field(default_factory=dict)


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
    tool_guidance: str = ""
    memory_enabled: bool = False
    lessons_enabled: bool = False
    params: LLMParams = Field(default_factory=LLMParams)
    tools: list[ToolBinding] = Field(default_factory=list)
    children: list[ChildLink] = Field(default_factory=list)


class AgentGraph(BaseModel):
    root_id: str
    agents: dict[str, AgentSpec]
