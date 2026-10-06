from typing import Literal
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class BudgetSpec(BaseModel):
    max_llm_calls: int = 30
    max_total_tokens: int = 200_000
    max_cost_usd: float | None = 0.50
    max_seconds: int = 300


class RunOptions(BaseModel):
    budget: BudgetSpec = Field(default_factory=BudgetSpec)
    parallel_tools: bool = False
    max_depth: int = 4
    max_iterations: int = 10
    scenario: str | None = None


class RunRequest(BaseModel):
    execution_id: str
    project_id: str
    root_agent_id: str
    task: str
    history: list[ChatMessage] = Field(default_factory=list)
    options: RunOptions = Field(default_factory=RunOptions)


class Totals(BaseModel):
    llm_calls: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float | None = None


RunStatus = Literal["completed", "error", "cancelled", "budget_exceeded"]


class RunResult(BaseModel):
    status: RunStatus
    final_output: str = ""
    error: str | None = None
    totals: Totals = Field(default_factory=Totals)
