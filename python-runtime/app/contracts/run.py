"""C-1: run request and result. Pure data (see docs/CONTRACTS.md)."""
from typing import Literal

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class AttachmentRef(BaseModel):
    """A file the user attached to the message.

    The platform copies it into the run workspace BEFORE starting the run; the core
    only ever sees this reference, never the bytes.
    """
    path: str                              # relative to the run workspace
    mime: str | None = None
    name: str | None = None                # original file name, for display


class BudgetSpec(BaseModel):
    max_llm_calls: int = 30
    max_total_tokens: int = 200_000
    max_cost_usd: float | None = 0.50      # None = no cost cap (local models cost 0, so calls/tokens/seconds are the real limits)
    max_seconds: int = 300


class MemoryOptions(BaseModel):
    episodic: bool = True                  # <recent_runs> block and recall_run tool
    intents: bool = False                  # reminders (intent tools and <reminders> block)
    embedding_model: str | None = None     # None = keyword-only memory search
    recall_budget_tokens: int = 800
    max_items_per_agent: int = 500


class RunOptions(BaseModel):
    budget: BudgetSpec = BudgetSpec()
    parallel_tools: bool = False           # run several tool calls of one turn concurrently
    max_parallel_tool_calls: int = 4       # hard per-execution tool limit
    tool_timeout_seconds: int = 120        # maximum duration for one tool invocation
    max_tasks: int = 100                   # maximum tasks in a scheduler plan
    max_depth: int = 4                     # sub-agent nesting
    max_iterations: int = 10               # LLM turns per agent
    scenario: str | None = None            # FakeRunner only
    memory: MemoryOptions = MemoryOptions()
    timezone: str = "UTC"                  # IANA name, so "tomorrow at 9" can be resolved
    # Model aliases the core resolves itself (see models.yaml). Keys: "fast",
    # "summarizer_model", "reflection_model", "vision_model". Values: "provider/model".
    # Empty = use the core's defaults.
    llm_aliases: dict[str, str] = {}


class RunRequest(BaseModel):
    execution_id: str
    project_id: str
    root_agent_id: str
    task: str                              # the latest user message
    history: list[ChatMessage] = []        # earlier turns NOT covered by history_summary (oldest first)
    history_summary: str = ""              # summary of older messages that are no longer in `history`
    attachments: list[AttachmentRef] = []  # files attached to `task`
    options: RunOptions = RunOptions()


class Totals(BaseModel):
    llm_calls: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float | None = None          # None = pricing unknown for a model used


RunStatus = Literal["completed", "error", "cancelled", "budget_exceeded"]


class RunResult(BaseModel):
    status: RunStatus
    final_output: str = ""
    error: str | None = None
    totals: Totals = Totals()
    new_summary: str | None = None         # set only if the core compacted the conversation this run
    summarized_count: int = 0              # how many leading messages of `history` new_summary now covers
