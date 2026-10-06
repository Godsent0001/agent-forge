# CONTRACTS v1: the shared interfaces

> Status: **draft v1.1** until task S-02 (the contracts session). After S-02, any change goes through a PR labelled `contract` that both of you approve.
> The code blocks below are copied from `python-runtime/app/contracts/` and `src/contracts.ts`, which are in the same PR. If they ever differ, fix the difference in a `contract` PR.

## What changed since the first draft

- **C-1:** `history_summary` (request) and `new_summary` / `summarized_count` (result) for conversation compaction; `attachments`; `RunOptions.memory`, `RunOptions.timezone`, `RunOptions.llm_aliases`.
- **C-2:** well-known `llm_call` names (`memory_extract`, `compaction`, `trim_summary`, `embed`); new `tool_call` end keys (`truncated`, `saved_result`, `result_data`); structure rules S1 to S4 next to R1 to R6.
- **C-3:** `ToolResult.truncated` and `next_offset`; `RunWorkspace.write_result`; the pagination and saved-results conventions; `CancelToken` now lives in `tools.py` (re-exported by `runner.py`).
- **C-4:** `LLMParams.reasoning`.
- **C-5:** `Runner.run` also takes `lessons`, `intents`, `run_history` and an optional `clock`, so the Runner interface does not reopen at A-06 / A-07.
- **C-6:** replaced by the v2 memory contracts (semantic memory, run history, intents, insights); lessons stay a draft.
- **C-7:** image parts, `response_format`, `reasoning_text` (AI-owned, documented here only).
- **C-8:** attachments on start; memory, intents, insights, notifications, maintenance and settings routes; richer `/v2/models`.
- **C-10:** Q9 to Q12 answered by ADR-002; Q13 to Q15 added.

## Why this file exists

Dev builds the platform (API, database, UI). AI builds the agent core (LLM calls, the loop, prompts, memory). If you agree on the shapes below **first**, neither of you waits for the other:

- Dev works against a **FakeRunner** that emits scripted events, so the UI, API and database can be built and tested with no LLM at all.
- AI works against a **FakeLLM** that returns scripted answers, so the core can be built and tested with no UI, no API key and no cost.
- Integration day (S-03) is then just swapping the fake for the real thing.

**Rules**
1. Code lives in `python-runtime/app/contracts/` and `src/contracts.ts`. They must match this file exactly.
2. Contracts are **pure data** (pydantic models, enums, protocols, small constants). No database, no network. The one exception is `app/contracts/checks.py` (no I/O): the event-stream checker and the example trace, shared by tests, the FakeRunner and the real Runner. `naming.py` holds two tiny pure functions.
3. The core (`app/core/`) never imports SQLAlchemy models or FastAPI. The platform (`routers/`, `services/`, UI) never imports prompt or LLM code. They only meet through this file.
4. To change a contract: one PR labelled `contract` that updates this file, the Python models and the TS types together. Both approve.

---

## C-1 Run request and result

```python
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
```

Execution status in the API and database also has two non-Runner values: `running` and `interrupted` (the app was closed or crashed mid-run).

`history` holds only the messages **not** covered by `history_summary`. When the core compacts a conversation it returns `new_summary` plus `summarized_count`; the platform stores both on the conversation and from then on sends only the newer messages plus `history_summary`.

---

## C-2 Events (the trace)

Every run produces a stream of events. Spans form a tree: `agent` → (`llm_call` | `tool_call`)\*. A `tool_call` that delegates to a sub-agent has exactly one child `agent` span.

```python
"""C-2: events (the trace). Pure data (see docs/CONTRACTS.md)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

EventType = Literal["execution_started", "span_started", "span_ended",
                    "approval_requested", "approval_resolved", "execution_ended"]
SpanKind = Literal["agent", "llm_call", "tool_call"]
SpanStatus = Literal["ok", "error", "cancelled"]

# R5 limits
EVENT_STRING_LIMIT = 2_000
EVENT_DATA_LIMIT_BYTES = 8 * 1024

# `name` values the core gives to llm_call spans that are not a normal agent turn.
WELL_KNOWN_LLM_CALL_NAMES = ("memory_extract", "compaction", "trim_summary", "embed")


class EventDraft(BaseModel):
    """What the Runner passes to emit(). The emitter fills execution_id, seq, ts."""
    type: EventType
    span_id: str | None = None
    parent_span_id: str | None = None
    kind: SpanKind | None = None
    name: str | None = None
    status: SpanStatus | None = None        # set on span_ended
    data: dict = {}


class RunEvent(EventDraft):
    execution_id: str
    seq: int                                # 1, 2, 3... no gaps, per execution
    ts: datetime                            # UTC
```

```ts
// Mirrors docs/CONTRACTS.md and python-runtime/app/contracts/*.py. Change them together (PR label `contract`).
// Dates are ISO-8601 UTC strings. API responses never include embedding vectors.

// ---- C-1 run -------------------------------------------------------------
export interface ChatMessage { role: "user" | "assistant"; content: string }
export interface AttachmentRef { path: string; mime?: string | null; name?: string | null }
export interface BudgetSpec {
  max_llm_calls: number; max_total_tokens: number; max_cost_usd: number | null; max_seconds: number;
}
export interface MemoryOptions {
  episodic: boolean; intents: boolean; embedding_model: string | null;
  recall_budget_tokens: number; max_items_per_agent: number;
}
export interface RunOptions {
  budget: BudgetSpec; parallel_tools: boolean; max_depth: number; max_iterations: number;
  scenario?: string | null; memory: MemoryOptions; timezone: string;
  llm_aliases: Record<string, string>;
}
/** Body of POST /v2/executions (the platform fills execution_id). */
export interface StartRunBody {
  project_id: string; root_agent_id: string; task: string;
  history?: ChatMessage[]; attachments?: AttachmentRef[]; options?: Partial<RunOptions>;
}
export interface Totals {
  llm_calls: number; tool_calls: number;
  input_tokens: number; output_tokens: number; cache_read_tokens: number;
  cost_usd: number | null;
}
export type RunStatus = "running" | "completed" | "error" | "cancelled"
  | "budget_exceeded" | "interrupted";

// ---- C-2 events ----------------------------------------------------------
export type EventType = "execution_started" | "span_started" | "span_ended"
  | "approval_requested" | "approval_resolved" | "execution_ended";
export type SpanKind = "agent" | "llm_call" | "tool_call";
export type SpanStatus = "ok" | "error" | "cancelled";

export interface RunEvent {
  execution_id: string;
  seq: number;
  ts: string;
  type: EventType;
  span_id?: string | null;
  parent_span_id?: string | null;
  kind?: SpanKind | null;
  name?: string | null;
  status?: SpanStatus | null;
  data: Record<string, unknown>;
}

// ---- C-6 memory, intents, insights ----------------------------------------
export type MemoryKind = "fact" | "preference" | "decision";
export type MemorySource = "user_stated" | "user_edited" | "inferred";
export type MemoryStatus = "active" | "superseded" | "archived";
export interface MemoryItem {
  id: string; agent_id: string; text: string; kind: MemoryKind;
  source_type: MemorySource; source_execution_id: string | null; evidence: string;
  created_at: string; last_used_at: string | null; use_count: number;
  pinned: boolean; status: MemoryStatus; expires_at: string | null;
}
export type IntentTrigger = "next_run" | "at_time";
export type IntentMode = "remind" | "auto_run";
export type IntentStatus = "active" | "fired" | "cancelled" | "expired";
export interface Intent {
  id: string; agent_id: string; text: string; trigger: IntentTrigger;
  due_at: string | null; repeat: "none" | "daily" | "weekly"; mode: IntentMode;
  status: IntentStatus; evidence: string; source_execution_id: string | null;
  created_at: string; last_fired_at: string | null;
}
export type InsightStatus = "pending" | "accepted" | "dismissed";
export interface Insight {
  id: string; agent_id: string; text: string; kind: "pattern" | "suggestion";
  evidence_execution_ids: string[]; status: InsightStatus;
  maintenance_run_id: string | null; created_at: string;
}

// ---- C-8 platform-only shapes -------------------------------------------
export interface Notification {
  id: string; kind: "intent_due" | "insight_ready" | "maintenance_failed";
  title: string; body: string; ref_id: string | null; created_at: string; read_at: string | null;
}
export interface MaintenanceRun {
  id: string; kind: "dream" | "embed_backfill"; started_at: string; ended_at: string | null;
  status: "running" | "ok" | "error"; cost_usd: number | null; detail: Record<string, unknown>;
}
export interface ModelInfo {
  provider: string; model: string; tier: string; kind: "chat" | "embedding";
  context_window: number | null; supports_tools: boolean; supports_vision: boolean;
  price_in: number | null; price_out: number | null;
}
```

### What goes in `data`

| type | kind | `data` keys |
|---|---|---|
| `execution_started` | n/a | `root_agent_id`, `task_preview` |
| `span_started` | `agent` | `agent_id`, `depth`, `input_preview` |
| `span_ended` | `agent` | `output_preview` |
| `span_started` | `llm_call` | `provider`, `model`, `message_count` (for `embed`: number of texts) |
| `span_ended` | `llm_call` | `usage` {`input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`}, `cost_usd`, `finish_reason`, `tool_calls` (list of names) |
| `span_started` | `tool_call` | `tool_name`, `tool_call_id`, `args` (truncated JSON) |
| `span_ended` | `tool_call` | `result_preview`, `is_error`, `artifacts` (list of relative paths), `truncated` (bool: the tool or the Runner cut the result), `saved_result` (relative path under `.results/`, or null), `result_data` (optional: `ToolResult.data` for the UI, e.g. the `plan` list; subject to R5) |
| `approval_requested` | n/a | `approval_id`, `tool`, `permissions`, `args_preview`, `reason` |
| `approval_resolved` | n/a | `approval_id`, `decision` (`allow_once` / `allow_run` / `deny` / `timeout`) |
| `execution_ended` | n/a | `status`, `final_output`, `totals`, `error` |

`llm_call` spans that are not a normal agent turn carry a `name`: `memory_extract`, `compaction`, `trim_summary` or `embed` (see `WELL_KNOWN_LLM_CALL_NAMES`). A normal turn has no name. They are children of the root agent span.

### Emission rules

- **R1.** Every `span_started` gets exactly one `span_ended`, even on error or cancel (emit it from a `finally` block, with `status` = `ok` / `error` / `cancelled`).
- **R2.** A parent's `span_ended` comes after the `span_ended` of all its children, and no child starts after its parent has ended.
- **R3.** `seq` starts at 1 and goes up by exactly 1 per event within an execution. The emitter assigns it; the Runner never sets it.
- **R4.** `execution_started` is first and `execution_ended` is last. Both are emitted by the platform (Dev), not the Runner.
- **R5.** Truncation: any string in `data` longer than 2,000 characters is cut and ends with `…[+N chars]`. The whole `data` object stays under 8 KB. Full prompts and results are not in events (see Q2). Event data never contains image bytes or embedding vectors.
- **R6.** `span_id` and `parent_span_id` are uuid4 strings. A root `agent` span has `parent_span_id = null`.

Structure rules (also checked by `checks.py`):
- **S1.** A run has exactly one root span, and it is an `agent` span.
- **S2.** An `llm_call` or `tool_call` span is a child of an `agent` span.
- **S3.** An `agent` span that is not the root is a child of a `tool_call` span.
- **S4.** A `tool_call` span has at most one child, and it is an `agent` span.

### Example: CEO delegates to Research, which searches the web

| seq | type | kind | name | span → parent |
|---|---|---|---|---|
| 1 | execution_started | | | |
| 2 | span_started | agent | CEO Agent | s1 → null |
| 3 | span_started | llm_call | | s2 → s1 |
| 4 | span_ended | llm_call | | s2 (tool_calls: research_agent) |
| 5 | span_started | tool_call | research_agent | s3 → s1 |
| 6 | span_started | agent | Research Agent | s4 → s3 |
| 7 | span_started | llm_call | | s5 → s4 |
| 8 | span_ended | llm_call | | s5 (tool_calls: web_search) |
| 9 | span_started | tool_call | web_search | s6 → s4 |
| 10 | span_ended | tool_call | | s6 |
| 11 | span_started | llm_call | | s7 → s4 |
| 12 | span_ended | llm_call | | s7 (final text) |
| 13 | span_ended | agent | | s4 |
| 14 | span_ended | tool_call | | s3 |
| 15 | span_started | llm_call | | s8 → s1 |
| 16 | span_ended | llm_call | | s8 |
| 17 | span_ended | agent | | s1 |
| 18 | execution_ended | | | |

`checks.example_events()` builds this sequence and `checks.check_events()` verifies R1 to R6 and S1 to S4. `tests/test_contracts.py` uses both; D-05 (FakeRunner) and A-03 (Runner) reuse the checker.

---

## C-3 Tools (v2)

```python
"""C-3: tools (v2). Pure data and protocols (see docs/CONTRACTS.md)."""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar, Literal, Protocol

from pydantic import BaseModel

Permission = Literal["net", "fs_write", "subprocess"]

DEFAULT_MAX_RESULT_CHARS = 6_000     # what the model sees of one tool result, before the head+pointer rule
SAVE_RESULT_OVER_CHARS = 1_000       # results longer than this are also saved to .results/ (C-9)


class ArtifactRef(BaseModel):
    path: str                    # relative to the run workspace
    mime: str | None = None
    description: str | None = None


class ToolResult(BaseModel):
    ok: bool = True
    content: str                 # what the model sees (the Runner truncates it)
    artifacts: list[ArtifactRef] = []
    data: dict | None = None     # structured payload for the UI only
    truncated: bool = False      # the tool itself returned only part of the data
    next_offset: int | None = None   # where to continue when truncated (pagination convention, C-9)


class ToolError(Exception):
    """Expected failure (bad input, missing binary, denied...). The model sees the message."""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.message = message
        self.retryable = retryable


class CancelToken(Protocol):
    @property
    def cancelled(self) -> bool: ...
    def raise_if_cancelled(self) -> None: ...        # raises asyncio.CancelledError


class RunWorkspace(Protocol):
    root: Path                                   # <data_dir>/runs/<execution_id>/
    def resolve(self, rel: str) -> Path: ...     # raises ToolError on absolute paths, "..", symlink escapes
    def new_path(self, name: str) -> Path: ...   # safe, unique file path inside the workspace
    def relative(self, p: Path) -> str: ...
    def write_result(self, tool_call_id: str, content: str) -> ArtifactRef: ...
    # writes <root>/.results/<tool_call_id>.txt and returns its reference (used to save long tool results)


class ToolContext(Protocol):
    execution_id: str
    span_id: str
    workspace: RunWorkspace
    cancel: CancelToken
    config: dict                                 # ToolBinding.config


class Tool(ABC):
    kind: ClassVar[str]
    default_description: ClassVar[str]           # written FOR THE MODEL (see docs/TOOL-WRITING.md)
    Input: ClassVar[type[BaseModel]]             # the JSON Schema sent to the model comes from here
    permissions: ClassVar[set[Permission]] = set()

    @abstractmethod
    async def run(self, args: BaseModel, ctx: ToolContext) -> ToolResult: ...
```

Names shown to the model follow one rule, implemented once in `app/contracts/naming.py`:

```python
"""Tool-name rule, implemented once (C-3, C-9)."""
import re

TOOL_NAME_RE = r"^[a-z][a-z0-9_-]{0,63}$"
_MAX_LEN = 64
_BAD = re.compile(r"[^a-z0-9_-]")


def sanitize_tool_name(name: str) -> str:
    """Lower-case, other characters become '_', must start with a letter, at most 64 chars."""
    s = _BAD.sub("_", (name or "").strip().lower())
    if not s or not s[0].isalpha() or not s[0].isascii():
        s = "t_" + s
    return s[:_MAX_LEN]


def dedupe_names(names: list[str]) -> list[str]:
    """['x', 'x', 'x'] -> ['x', 'x_2', 'x_3']. Keeps order; never returns a duplicate."""
    used: set[str] = set()
    out: list[str] = []
    for name in names:
        candidate, n = name, 1
        while candidate in used:
            n += 1
            suffix = f"_{n}"
            candidate = name[: _MAX_LEN - len(suffix)] + suffix
        used.add(candidate)
        out.append(candidate)
    return out
```

Old string-in/string-out tools are wrapped by `LegacyToolAdapter` (D-08): its `Input` is `{"input": str}`.

**Pagination convention.** A tool that can return long output has `offset: int = 0` and `limit: int` in its `Input`. When it returns only part of the data it sets `truncated=True` and `next_offset`, and says so in `content` ("showing lines 1 to 200 of 9,400; call again with offset=200").

**Saved results.** The Runner writes every tool result longer than `SAVE_RESULT_OVER_CHARS` (1,000) through `workspace.write_result(...)` to `.results/<tool_call_id>.txt`. The model sees the full text up to `max_result_chars`; above that it sees the head plus `…[truncated N chars; full result saved at <path>; read a range or search it]`. The span's `saved_result` records the path. The `.results/` folder lives and dies with the run workspace.

---

## C-4 Agent graph (what the core sees)

The platform loads the database into plain objects. The core never touches SQLAlchemy.

```python
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
```

---

## C-5 The Runner and what the platform gives it

```python
"""C-5: the Runner and what the platform gives it. Protocols (see docs/CONTRACTS.md)."""
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Protocol

from .events import EventDraft
from .graph import AgentGraph, ToolBinding
from .memory import IntentStore, LessonStore, MemoryStore, RunHistory
from .run import RunRequest, RunResult
from .tools import CancelToken, Permission, RunWorkspace, Tool

Emit = Callable[[EventDraft], Awaitable[None]]
Clock = Callable[[], datetime]          # returns timezone-aware UTC; tests pass a fake


class ApprovalGate(Protocol):
    async def check(self, *, tool: str, permissions: set[Permission], args_preview: str,
                    span_id: str, force: bool = False, reason: str = "") -> bool: ...
    # True = go ahead, False = denied. The gate emits approval_requested / approval_resolved itself.


class ToolFactory(Protocol):
    def build(self, binding: ToolBinding) -> Tool: ...


class Runner(Protocol):
    async def run(self, req: RunRequest, *, graph: AgentGraph, emit: Emit, cancel: CancelToken,
                  approvals: ApprovalGate, workspace: RunWorkspace, tools: ToolFactory,
                  memory: MemoryStore, lessons: LessonStore, intents: IntentStore,
                  run_history: RunHistory, clock: Clock | None = None) -> RunResult: ...


__all__ = ["Emit", "Clock", "CancelToken", "ApprovalGate", "ToolFactory", "Runner"]
```

| Piece | Built by | Lives in |
|---|---|---|
| `Runner` (real) | AI | `app/core/runner.py` |
| `FakeRunner` | Dev | `app/dev/fake_runner.py` |
| `graph` loader | Dev | `app/services/graph_loader.py` |
| `emit` (assigns seq, saves, broadcasts) | Dev | `app/services/executions.py` |
| `cancel`, `approvals` | Dev | `app/services/executions.py`, `app/infra/approvals.py` |
| `tools` (`ToolFactory`) | Dev | `app/tools/registry.py` |
| `workspace` | Dev | `app/infra/workspace.py` |
| `memory` (SQL-backed) | Dev (protocol by AI) | `app/services/memory_store.py` |
| `run_history` | Dev | `app/services/run_history.py` |
| `intents`, `lessons` | Dev | `app/services/intent_store.py`, `app/services/lesson_store.py` |
| `clock` | Dev (tests pass a fake) | defaults to real UTC time |

Until their cards land, S-03 passes **no-op** `memory`, `lessons`, `intents` and `run_history` implementations (the core ships `InMemory*` versions in A-06a).

---

## C-6 Memory, run history, intents, insights, lessons

Details and behavior: `docs/MEMORY.md`. Shapes:

```python
"""C-6: memory, run history, intents, insights, lessons. Pure data and protocols
(see docs/CONTRACTS.md and docs/MEMORY.md)."""
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel

# ---- limits (MEMORY.md) -------------------------------------------------
MAX_MEMORY_TEXT_CHARS = 200
MAX_INTENT_TEXT_CHARS = 300
MAX_INSIGHT_TEXT_CHARS = 300

# ---- semantic memory ----------------------------------------------------
MemoryKind = Literal["fact", "preference", "decision"]
# user_stated: said by the user. user_edited: typed in the UI.
# inferred: found by a dream and ACCEPTED by the user.
MemorySource = Literal["user_stated", "user_edited", "inferred"]
MemoryStatus = Literal["active", "superseded", "archived"]


class MemoryCandidate(BaseModel):
    text: str                                # one self-contained statement, max 200 chars
    kind: MemoryKind = "fact"
    source_type: MemorySource = "user_stated"
    source_execution_id: str | None = None
    evidence: str = ""                       # verbatim user quote (checked by the core)
    supersedes: list[str] = []               # ids of existing items this one replaces
    expires_at: datetime | None = None
    embedding: list[float] | None = None     # never sent to the UI
    embedding_model: str | None = None


class MemoryItem(MemoryCandidate):
    id: str
    agent_id: str
    created_at: datetime
    last_used_at: datetime | None = None
    use_count: int = 0
    pinned: bool = False
    status: MemoryStatus = "active"


class MemoryHit(BaseModel):
    item: MemoryItem
    keyword_score: float = 0.0               # 0..1 (FTS5 bm25, normalized)
    vector_score: float = 0.0                # 0..1 cosine; 0 if no usable embedding


class MemoryStore(Protocol):
    # Reads return only active, non-expired items.
    async def pinned(self, agent_id: str) -> list[MemoryItem]: ...
    async def candidates(self, agent_id: str, query: str, limit: int, *,
                         query_embedding: list[float] | None = None,
                         embedding_model: str | None = None) -> list[MemoryHit]: ...
    async def related(self, agent_id: str, text: str, limit: int) -> list[MemoryItem]: ...
    async def add(self, agent_id: str, items: list[MemoryCandidate]) -> list[MemoryItem]: ...
    # add() also marks `supersedes` targets "superseded", in one transaction.
    async def touch(self, ids: list[str], execution_id: str) -> None: ...
    async def missing_embeddings(self, agent_id: str, model: str, limit: int) -> list[MemoryItem]: ...
    async def set_embeddings(self, pairs: list[tuple[str, list[float], str]]) -> None: ...  # (id, vector, model)


# ---- episodic memory (read-only view over past runs) --------------------
class RunDigest(BaseModel):
    execution_id: str
    agent_id: str
    started_at: datetime
    task_preview: str
    status: str
    final_output_preview: str = ""
    errors: list[str] = []                   # up to 3, each cut to 200 chars (tool/LLM error text: UNTRUSTED)
    feedback: Literal["up", "down"] | None = None


class RunHistory(Protocol):
    async def search(self, agent_id: str, query: str, limit: int) -> list[RunDigest]: ...
    async def recent(self, agent_id: str, *, since: datetime, limit: int,
                     only_problems: bool = False) -> list[RunDigest]: ...


# ---- standing intents (reminders) ---------------------------------------
IntentTrigger = Literal["next_run", "at_time"]
IntentMode = Literal["remind", "auto_run"]
IntentStatus = Literal["active", "fired", "cancelled", "expired"]


class Intent(BaseModel):
    id: str
    agent_id: str
    text: str                                # max 300 chars: what to remind or do
    trigger: IntentTrigger
    due_at: datetime | None = None           # UTC; required for at_time
    repeat: Literal["none", "daily", "weekly"] = "none"
    mode: IntentMode = "remind"              # auto_run can ONLY be set from the UI
    status: IntentStatus = "active"
    evidence: str = ""                       # verbatim user quote
    source_execution_id: str | None = None
    created_at: datetime
    last_fired_at: datetime | None = None


class IntentStore(Protocol):
    async def create(self, intent: Intent) -> Intent: ...
    async def due_for_run(self, agent_id: str, now: datetime) -> list[Intent]: ...  # active and (next_run, or at_time <= now)
    async def mark_fired(self, ids: list[str], now: datetime) -> None: ...          # applies `repeat`, else status "fired"
    async def cancel(self, intent_id: str) -> None: ...
    async def list(self, agent_id: str, status: IntentStatus | None = None) -> list[Intent]: ...


# ---- insights ("dreams"): suggestions only, until the user accepts ------
InsightStatus = Literal["pending", "accepted", "dismissed"]


class Insight(BaseModel):
    id: str
    agent_id: str
    text: str                                # max 300 chars
    kind: Literal["pattern", "suggestion"]
    evidence_execution_ids: list[str]
    status: InsightStatus = "pending"
    maintenance_run_id: str | None = None
    created_at: datetime


class InsightStore(Protocol):
    async def add(self, items: list[Insight]) -> None: ...
    async def list(self, agent_id: str, status: InsightStatus | None = None) -> list[Insight]: ...
    async def resolve(self, insight_id: str, status: InsightStatus) -> None: ...
    # Accepting also writes a MemoryItem (source_type="inferred") in the same transaction (platform).


# ---- lessons (draft: A-07 may extend this through a `contract` PR) ------
class Lesson(BaseModel):
    id: str
    agent_id: str
    text: str
    evidence_execution_id: str | None = None
    status: Literal["active", "archived"] = "active"
    score: float = 0.0
    created_at: datetime


class LessonStore(Protocol):
    async def active(self, agent_id: str, limit: int) -> list[Lesson]: ...
    async def add(self, lesson: Lesson) -> None: ...
```

The API never returns `embedding` or `embedding_model` to the UI.

---

## C-7 LLM types (AI-owned; listed so Dev knows what `usage` looks like)

```python
# app/core/llm/types.py  (not in contracts/; AI may change freely as long as events keep C-2's shape)
class TextPart(BaseModel):  type: Literal["text"] = "text";   text: str
class ImagePart(BaseModel): type: Literal["image"] = "image"; path: str; mime: str
# ImagePart.path is workspace-relative. Bytes are read and base64-encoded only at the backend edge,
# never stored in events or logs. A message's content is `str` or `list[TextPart | ImagePart]`.

class ToolSpec(BaseModel):  name: str; description: str; parameters: dict   # JSON Schema
class ToolCall(BaseModel):  id: str; name: str; arguments: dict; arguments_error: str | None = None
class Usage(BaseModel):     input_tokens: int = 0; output_tokens: int = 0; cache_read_tokens: int = 0; cache_write_tokens: int = 0

# Per-call extras on the LLM backend: response_format: dict | None  (a JSON Schema, e.g. Ollama structured output)
# and reasoning (from LLMParams.reasoning).

class LLMTurn(BaseModel):
    message: dict                # assistant message in OpenAI-style form; appended to history verbatim
    text: str | None
    tool_calls: list[ToolCall]   # empty list = final answer
    usage: Usage
    cost_usd: float | None
    finish_reason: str
    model: str
    reasoning_text: str | None = None   # thinking text; never replayed, never in events, never in the answer

# Embeddings (core-owned): Embedder.embed(texts: list[str]) -> list[list[float]]
```

---

## C-8 HTTP API v2

All routes except `/health` need `Authorization: Bearer <token>` (D-10). Errors are `{"detail": "message"}`. Response shapes are in `src/contracts.ts` and `app/contracts/memory.py` / `api.py`.

| Method | Path | Body / query | Returns |
|---|---|---|---|
| POST | `/v2/executions` | `StartRunBody`: `{project_id, root_agent_id, task, history?, attachments?, options?}` | `{id, status: "running"}` **immediately** |
| GET | `/v2/executions?project_id=&limit=` | | list of `{id, task_preview, status, started_at, ended_at, totals}` |
| GET | `/v2/executions/{id}` | | `{id, status, final_output, totals, error, started_at, ended_at}` |
| GET | `/v2/executions/{id}/events?after_seq=0` | | `RunEvent[]` ordered by `seq` |
| WS | `/v2/executions/{id}/stream?after_seq=0&token=` | | pushes `RunEvent` JSON: replays after `after_seq`, then live |
| POST | `/v2/executions/{id}/cancel` | | `{status: "cancelling"}` |
| POST | `/v2/executions/{id}/approvals/{approval_id}` | `{decision: "allow_once" \| "allow_run" \| "deny"}` | `{ok: true}` |
| GET | `/v2/executions/{id}/files/{relpath}` | token in header or `?token=` | file bytes (run workspace only) |
| GET | `/v2/models` | | `ModelInfo[]` (`kind`: chat or embedding; `supports_tools`, `supports_vision`, `context_window`; local models have price 0.0) |
| GET | `/v2/system/check` | | `[{name, ok, detail, fix}]` (includes FTS5 and Ollama checks) |
| POST | `/v2/settings/keys` | `{anthropic?, openai?, google?}` | `{status: "ok"}` |
| GET / PUT | `/v2/projects/{project_id}/settings` | settings JSON (keys in C-9) | settings JSON |
| GET | `/v2/agents/{agent_id}/memory?q=&status=` | | `MemoryItem[]` |
| PATCH | `/v2/memory/{id}` | `{text?, pinned?, status?}` | `MemoryItem` (a text edit sets `source_type = user_edited`) |
| DELETE | `/v2/memory/{id}` | | `{ok: true}` |
| DELETE | `/v2/agents/{agent_id}/memory` | | `{ok: true, deleted: n}` (clear all; the UI asks to confirm) |
| GET | `/v2/agents/{agent_id}/memory/export` | | `text/markdown` |
| GET | `/v2/agents/{agent_id}/intents?status=` | | `Intent[]` |
| POST | `/v2/agents/{agent_id}/intents` | `{text, trigger, due_at?, repeat?}` | `Intent` (always `mode = remind`) |
| PATCH | `/v2/intents/{id}` | `{text?, due_at?, repeat?, mode?, status?}` | `Intent` (**the only place `mode` can become `auto_run`**) |
| GET | `/v2/agents/{agent_id}/insights?status=` | | `Insight[]` |
| POST | `/v2/insights/{id}/resolve` | `{status: "accepted" \| "dismissed", as?: "memory" \| "lesson"}` | `{ok: true}` |
| GET | `/v2/notifications?unread=1` | | `Notification[]` |
| POST | `/v2/notifications/{id}/read` | | `{ok: true}` |
| GET | `/v2/maintenance-runs?limit=` | | `MaintenanceRun[]` |

The old `/executions` routes stay until S-04. Nothing in `/v2` may depend on them.

---

## C-9 Conventions and limits

- IDs are uuid4 strings. Timestamps are ISO-8601 UTC (`datetime` objects in Python must be timezone-aware UTC).
- Tool, agent-tool and span names follow `TOOL_NAME_RE`. Display names (`AgentSpec.name`) can be anything.
- Tool result sent to the model: at most `max_result_chars` (default 6,000, `DEFAULT_MAX_RESULT_CHARS`). Longer results follow the saved-results rule in C-3.
- Event `data`: strings over 2,000 characters are truncated; whole object under 8 KB (R5). No image bytes, no embeddings.
- Costs: USD floats. Unknown pricing is `null` and the UI shows "n/a". Local models (Ollama) have an explicit price of `0.0`, so calls, tokens and seconds are the real budget limits.
- A tool must never write outside `ctx.workspace`, and never needs an absolute path from the model.
- Memory limits (`MAX_MEMORY_TEXT_CHARS` 200, `MAX_INTENT_TEXT_CHARS` 300, `MAX_INSIGHT_TEXT_CHARS` 300) and defaults (500 items per agent, 800 recall tokens, 20 active intents per agent, 3 auto-runs a day, $0.10 per auto-run) are in `docs/MEMORY.md`.
- Model aliases (`fast`, `summarizer_model`, `reflection_model`, `vision_model`) are resolved by the core from `models.yaml`; `RunOptions.llm_aliases` overrides them per run.
- Project settings JSON keys: `episodic_enabled`, `intents_enabled`, `dreams_enabled`, `embedding_model`, `recall_budget_tokens`, `max_items_per_agent`, `max_auto_runs_per_day`, `dream_idle_minutes`, `extraction_mode` (`inline` | `background`), `llm_aliases`.

---

## C-10 Open questions (answer them in S-02, write the answer under each)

Q1 to Q8 are still **proposals**: confirm or change each in the session and tick the box.

- [ ] **Q1.** Always emit `llm_call` spans? *Proposed: yes; the UI can hide them.*
- [ ] **Q2.** Store full prompts and responses for debugging? *Proposed: a "debug trace" setting (default on in dev, off otherwise) that saves full messages of each `llm_call` into a separate `span_payloads` table, capped at about 200 KB per run.*
- [ ] **Q3.** Parallel tool calls default? *Proposed: off, enabled per project. (A single local Ollama model serializes calls anyway.)*
- [ ] **Q4.** Where do budgets live? *Proposed: project default in settings, overridable per run.*
- [ ] **Q5.** Do sub-agents receive conversation history? *Proposed: no, only the `task` string the parent wrote.*
- [ ] **Q6.** Approval timeout? *Proposed: 5 minutes, then deny.*
- [ ] **Q7.** Does a depth-limit hit kill the run or return a tool error to the model? *Proposed: tool error (the model answers itself). A cycle in the graph is fatal.*
- [ ] **Q8.** Keep the `/v2` prefix after cut-over? *Proposed: yes, to avoid churn.*

Answered by ADR-002 (2026-10-06):
- **Q9.** Memory extraction runs **inline** at the end of a run (setting `extraction_mode` can switch to `background`).
- **Q10.** Memory limits stay as proposed (500 / 800 tokens / 20 / 3 a day / $0.10); all are settings.
- **Q11.** Embeddings are **off by default**; with Ollama detected, settings offers a one-click enable.
- **Q12.** `auto_run` reminders **ship, off by default**; only the user can enable them.

New, to confirm in S-02:
- [ ] **Q13.** Attachments: the platform copies the user's files into the run workspace and passes `AttachmentRef`s (no bytes in the request). *Proposed: yes.*
- [ ] **Q14.** `RunOptions.llm_aliases` lets project settings choose the summarizer, reflection and vision models. *Proposed: yes; empty means the core's defaults from `models.yaml`.*
- [ ] **Q15.** `Runner.run` takes `lessons` now (a no-op until A-07), so the Runner interface does not reopen later. *Proposed: yes.*
