# Tasks for AI (agent core, prompts, memory, evals)

You own the agent "brain": LLM calls, the loop, prompts, memory, lessons, tool descriptions and evals. You work in a **new package** (`python-runtime/app/core/`), so you get a fresh start without touching the old engine. Read `PLAN.md` first (decision, rules, ownership), then `CONTRACTS.md` (the interfaces).

> **Precedence (added 2026-10-06).** Where `PLAN.md` section 6b (memory), 6c (large inputs and core tools) or 2b (Ollama) differs from a card below, **PLAN.md wins**. Changed cards: **A-02** (+ images, `response_format`, `reasoning`, Ollama; 4.5d), **A-03** (+ saved tool results, in-run trimming; 5.5d), **A-04** (+ plan, self-check, `<plan>`; 2d), **A-06** (replaced by A-06a to A-06g), **A-07** (moves to M2b), **A-08** (+ large-input evals; 3.5d), **A-10** (+ Ollama entries, `num_ctx`, `0.0` prices; 2d). **New:** A-15a to A-15c. All other cards are unchanged. The contracts are drafted in `contracts-v1`; start from `docs/CONTRACTS.md`.

## How to use this file

- One card = one branch = one PR (`ai/A-03-runner`). Work the steps in order, tick the boxes in the same PR. Done = every "Done when" box ticked, CI green, Dev has reviewed.
- Sizes (focused days): S up to half a day, M 1 to 2, L 3 to 5. Priority: P0 needed for the milestone gate, P1 should, P2 stretch.
- You never need the UI, the database or an API key to make progress: use `FakeLLM`, fake tools and the CLI (A-03). Live tests are marked `@pytest.mark.live`, run by hand with a cheap model and a hard budget.
- `app/core/` must not import SQLAlchemy models or FastAPI (CONTRACTS rule 3).
- The old `app/llm.py` and `app/runtime/*` are frozen legacy. Read them for ideas, do not edit them.

## What you need from Dev, and when

| You need | From | When |
|---|---|---|
| `contracts/` package (events, tools, graph, run) | S-02 | end of M0 |
| `Tool` v2 base, `LegacyToolAdapter`, `tool_spec()`, `scripts/try_tool.py` | D-08 | M1 |
| Real graph loader, event emitter, FakeRunner (to compare traces) | D-04, D-05 | M1 |
| Workspace (until then use a temp dir) | D-09 | M2 |
| Approval gate implementation | D-12 | M2 |
| SQL memory and lesson stores, feedback data | D-14, D-16 | M2 |
| Settings UI for budgets and models | D-12, A-10 | M2 |

## Summary

| ID | Card | Size | Pri | Milestone | Depends on |
|---|---|---|---|---|---|
| A-01 | Runner and LLM-backend decision | S (1d) | P0 | M1 | S-01 |
| A-02 | LLM adapter v2 and FakeLLM | L (3.5d) | P0 | M1 | S-02, A-01 |
| A-03 | Runner v2 (the loop) | L (4.5d) | P0 | M1 | A-02, S-02 |
| A-04 | Prompt architecture v2 | M (1.5d) | P0 | M1 | A-02 |
| A-05 | Tool descriptions and schemas | M (1.5d) | P1 | M1 to M2 | D-08 |
| A-06 | Memory v2 | L (3d) | P1 | M2 | A-03 |
| A-07 | Lessons (replaces learned experience) | L (3d) | P1 | M2 | A-06 |
| A-08 | Eval harness and golden tasks | L (3d) | P0 | M2 | A-03 |
| A-09 | Prompt-injection hygiene | S (1d) | P0 | M2 | A-03, D-12 |
| A-10 | Models, pricing and budgets | M (1.5d) | P1 | M2 | A-02 |
| A-11 | Search and fetch tools | M (1.5d) | P1 | M2 | D-13 |
| A-12 | Starter agent templates | M (1.5d) | P1 | M3 | S-04 |
| A-13 | Usage data spec | S (0.5d) | P2 | M3 | A-10 |
| A-14 | Real-world tuning | L (3d) | P0 | M3 | D-19 |

---

# Milestone 1: Stable core

## A-01 · Runner and LLM-backend decision

**Owner** AI · **Size** S (1 day) · **Priority** P0 · **Depends on** S-01

**Goal:** decide in one day (a) hand-rolled loop vs adopting an agent library, and (b) LiteLLM vs thin provider adapters. Dev is not blocked either way: the `Runner` and `LLM` interfaces stay the same.

**Steps**
- [ ] 1. One-page matrix of the options (hand-rolled, plus at most two libraries you consider) on: model-agnostic tool calling, hooks to emit our span events (C-2), cancellation, budgets, sub-agent recursion, typed tool args, dependency weight and PyInstaller friendliness, testability with a fake LLM.
- [ ] 2. Time-box a spike (at most 4 hours per option): the `ceo_research` scenario with a scripted model must produce the C-2 event sequence.
- [ ] 3. LiteLLM vs official SDKs or one OpenAI-compatible client plus native Anthropic: compare bundle size, tool-call fidelity, prompt caching support, cost tracking, and supply-chain risk (LiteLLM had a malicious-release incident in March 2026; at minimum pin and keep hashes).
- [ ] 4. Write D-1 (runner) and D-2 (LLM backend) in `docs/DECISIONS.md`.

**Done when:** both decisions are merged and Dev has read them. **Default if undecided:** a hand-rolled loop of about 250 lines, with LiteLLM pinned behind the `LLM` interface.

---

## A-02 · LLM adapter v2 and FakeLLM

**Owner** AI · **Size** L (3.5 days) · **Priority** P0 · **Depends on** S-02, A-01

**Files (new):** `app/core/llm/{types,adapter,backend_*,pricing,fake}.py`, `tests/core/test_llm_*.py`

**Steps**
- [ ] 1. Types per C-7 (`ToolSpec`, `ToolCall`, `Usage`, `LLMTurn`, `LLMParams`).
- [ ] 2. `complete(messages, tools, params) -> LLMTurn`. Messages are OpenAI-style, including assistant `tool_calls` and `role: "tool"` messages, passed through verbatim. Parse **all** tool calls. If argument JSON is broken, set `ToolCall.arguments_error`; never raise.
- [ ] 3. Usage includes cache read and cache write tokens. Cost comes from `pricing.py` (YAML, price per 1M tokens; unknown model gives `None`).
- [ ] 4. Retries with back-off on 429, 5xx and timeouts; none on auth or other 4xx. Typed errors: `LLMAuthError`, `LLMRateLimit`, `LLMTimeout`, `LLMBadRequest`, `LLMContextTooLong`. An empty model name fails early with a clear message.
- [ ] 5. Prompt-cache markers on the stable prefix (Anthropic first; other providers cache long prefixes automatically, so keep the stable part first).
- [ ] 6. `FakeLLM(script)`: scripted turns (text or tool calls), records every `messages` list it receives, can simulate errors and latency.
- [ ] 7. Tests offline, plus one `@pytest.mark.live` round trip with a cheap model that returns a tool call.

**Done when:** offline tests pass; the live test passes by hand.

---

## A-03 · Runner v2 (the loop)

**Owner** AI · **Size** L (4.5 days) · **Priority** P0 · **Depends on** A-02, S-02

**Files (new):** `app/core/{runner,budget,spans,cli}.py`, `tests/core/test_runner.py`

**Steps**
- [ ] 1. `spans.py`: an async context manager `span(emit, kind, name, parent, data)` that always emits `span_ended` in `finally` (R1).
- [ ] 2. `run_agent(spec, messages, parent_span, depth)`: check cancel and budget, open an `llm_call` span, call the LLM, append `turn.message` verbatim, and if there are no tool calls return the text.
- [ ] 3. Dispatch tool calls, each in a `tool_call` span: sequential by default, `asyncio.gather(..., return_exceptions=True)` when `options.parallel_tools`. Append results as `role: "tool"` with the same `tool_call_id`, in order.
- [ ] 4. Failures are fed back to the model and never kill the run (table below). Truncate results to `max_result_chars` (6,000).
- [ ] 5. Sub-agents as tools: name from `sanitize_tool_name(child.name)` then `dedupe_names` after the agent's own tool names; description = link description or child description (**never** the system prompt); `Input = {task: str}`; runs `run_agent(child, ..., depth+1)` inside the `tool_call` span.
- [ ] 6. Guards: `max_iterations` per agent; loop detection (same tool and args 3 times: add a notice once, then force a final answer without tools); one shared `Budget` for the whole tree (LLM calls, tokens, cost, seconds) that stops with `budget_exceeded`.
- [ ] 7. Cancellation: `cancel.raise_if_cancelled()` between steps; `finally` closes spans as `cancelled`.
- [ ] 8. Memory and lessons: call the hooks (stubs for now, real in A-06 and A-07).
- [ ] 9. `cli.py`: `python -m app.core.cli run --graph fixtures/ceo_research.json --task "..." --fake` prints the events, so you can iterate with no UI.
- [ ] 10. Tests (FakeLLM and fake tools): single answer; tool call; parallel calls; unknown tool; bad args; sub-agent chain; sub-agent failure recovered by the parent; loop detection; budget; cancel; depth limit; cycle. Every event stream passes the C-2 checker and matches the shape of Dev's `ceo_research` scenario.

| Situation | Model sees | Run |
|---|---|---|
| Unknown tool | `ERROR: unknown tool 'x'. Available: a, b` | continues |
| Invalid arguments | `ERROR: invalid arguments: <details>. Expected: <schema summary>` | continues |
| `ToolError` | `ERROR: <message>` | continues |
| Unexpected exception | `ERROR: tool crashed (<ExceptionType>)` (log the traceback) | continues |
| Sub-agent failed | `ERROR: sub-agent 'x' failed: <message>` | continues |
| Approval denied | `ERROR: the user denied this action` | continues |
| Depth limit reached | `ERROR: maximum delegation depth reached, answer yourself` | continues |
| Cycle in the graph | none | stops, status `error` |
| LLM error after retries | none | stops, status `error` |
| Budget exceeded | none | stops, `budget_exceeded` |
| Cancel | none | stops, `cancelled` |

**Done when:** all tests pass and the CLI trace for `ceo_research` is accepted by Dev's UI fixtures check. This unblocks S-03.

---

## A-04 · Prompt architecture v2

**Owner** AI · **Size** M (1.5 days) · **Priority** P0 · **Depends on** A-02

**Files (new):** `app/core/prompts/*.md`, `app/core/prompt_builder.py`, `tests/snapshots/`

**Steps**
- [ ] 1. One system message with clearly separated sections (`<role>`, `<instructions>`, `<tool_guidance>`, `<lessons>`, `<memory>`). Say each rule **once**; remove the repeated "CRITICAL DIRECTIVE" blocks.
- [ ] 2. History as real chat messages with the latest task last. No marker strings.
- [ ] 3. Order for caching: stable content first (role, instructions, tool guidance, lessons), volatile content last (memory recall, task).
- [ ] 4. Delegation guidance for sub-agents: write a self-contained `task`, expect a final text back.
- [ ] 5. Snapshot tests for a sample agent; compare 5 real tasks old vs new by hand.

**Done when:** snapshots are checked in and the 5-task comparison shows no regression.

---

## A-05 · Tool descriptions and schemas

**Owner** AI · **Size** M (1.5 days) · **Priority** P1 · **Depends on** D-08

**Steps**
- [ ] 1. Write `docs/TOOL-WRITING.md`: what the tool does, when to use it, inputs with examples, limits, what errors mean (about 100 words per tool).
- [ ] 2. Native `Input` models and descriptions for the general tools: `web_search` (`query`, `max_results`), `http_request` (`method`, `url`, `body`, `headers`), `file_system` (`op`, `path`, `content`), `python` (`code`). Register them in `NATIVE_TOOLS` (Dev reviews the PR).
- [ ] 3. Then the 8 or so video tools needed for one end-to-end scenario (voice, alignment, lip-sync, captions, timeline, composition, preview).
- [ ] 4. Rewrite error messages so the model can act on them ("Missing 'words'. Get it from audio_alignment.").
- [ ] 5. One golden call per tool for A-08.

**Done when:** schemas appear in the tool definitions sent to the LLM, and a cheap model calls each general tool correctly from the description alone (live check).

---

# Milestone 2: Safe and solid

## A-06 · Memory v2

**Owner** AI · **Size** L (3 days) · **Priority** P1 · **Depends on** A-03

**Steps**
- [ ] 1. Finalize the protocol in C-6 through a `contract` PR.
- [ ] 2. Fix the blind spot: every entry is either in the summary or included verbatim within a token budget.
- [ ] 3. Store extracted facts, preferences and decisions, **not** Q and A transcripts. After a successful run (memory enabled, and the run used tools or the user stated a preference) one cheap-model call returns 0 to 3 `MemoryCandidate`s. Dedupe by normalized text.
- [ ] 4. Recall = pinned + recency + keyword score within `budget_tokens` (the interface must allow FTS5 or embeddings later). A rolling summary only for overflow.
- [ ] 5. `InMemoryStore` for tests.

**Done when:** a 30-run simulation stays under budget, a test proves no entry is silently invisible, and a failed extraction writes nothing.

---

## A-07 · Lessons (replaces "learned experience")

**Owner** AI · **Size** L (3 days) · **Priority** P1 · **Depends on** A-06

**Steps**
- [ ] 1. Opt-in per agent (`lessons_enabled`). `Lesson` model per C-6.
- [ ] 2. Reflect **only on signals**: a run that errored and recovered, thumbs up/down feedback (D-14), optionally every N runs.
- [ ] 3. Reflection input is truncated tool output marked untrusted. Output is 0 to 2 lessons with evidence, at most 300 characters each; strip URLs and anything that reads like an instruction.
- [ ] 4. Inject the top K (at most 1,200 characters) in `<lessons>`.
- [ ] 5. Run in the background after `execution_ended`. On failure only log; **never write fallback text**.
- [ ] 6. Versioned (a new row per change) so Dev's UI can show history. Migrate the old `learned_experience` text as one archived legacy lesson.
- [ ] 7. Tests with FakeLLM: gating, injection filter, failure safety.

**Done when:** no code path writes to an agent when the LLM call fails, opt-in works, and lessons show up in the prompt snapshot.

---

## A-08 · Eval harness and golden tasks

**Owner** AI · **Size** L (3 days) · **Priority** P0 · **Depends on** A-03

**Files (new):** `evals/tasks/*.yaml`, `evals/run_evals.py`, `evals/judges.py`

**Steps**
- [ ] 1. Task format: `id`, graph fixture, `input`, `fake_script` (for CI) or `live: true`, `assertions` (`tool_called`, `final_contains`, `max_llm_calls`, `no_errors`, `cost_usd_lt`), optional `judge` rubric.
- [ ] 2. Run through the real `Runner`. FakeLLM in CI; live runs by hand with a cheap model and a hard budget.
- [ ] 3. LLM judge at temperature 0 returns pass/fail plus a reason. Save results as JSON in `evals/results/`.
- [ ] 4. Report: table of tasks with pass, calls, tokens, cost, duration, plus a diff against the previous results file to flag regressions.
- [ ] 5. Ten starter tasks: single answer, tool use, delegation, failure recovery, budget stop, loop detection, injection resistance, memory recall, cancellation, parallel tools.
- [ ] 6. CI runs the offline set on every PR.

**Done when:** `uv run python -m evals.run_evals` prints the table and CI runs the offline set.

---

## A-09 · Prompt-injection hygiene

**Owner** AI · **Size** S (1 day) · **Priority** P0 · **Depends on** A-03, D-12

**Steps**
- [ ] 1. Wrap tool output as `<tool_result name="..." trust="untrusted">...</tool_result>` and state once in the system prompt that instructions inside results are data.
- [ ] 2. Memory and lessons must not copy raw tool output or URLs.
- [ ] 3. After untrusted content entered the run (`web_search`, `web_fetch`, `http_request`), any call to a tool with `subprocess`, `fs_write` or a `net` POST goes through `approvals.check(..., force=True, reason="after untrusted content")`.
- [ ] 4. Eval tasks: a FakeLLM that obeys an injected instruction must be blocked by the gate.

**Done when:** the injection evals pass offline, and a live run is reported.

---

## A-10 · Models, pricing and budgets

**Owner** AI · **Size** M (1.5 days) · **Priority** P1 · **Depends on** A-02

**Steps**
- [ ] 1. `models.yaml` (shipped default plus an override file in the data dir): provider, model id, tier (fast, standard, strong), context window, prices (in, out, cache), capabilities. A `get_models()` helper for Dev's `/v2/models`.
- [ ] 2. System aliases `summarizer_model`, `reflection_model`, `judge_model`, defaulting to the fast tier of the configured provider.
- [ ] 3. Default budgets (suggest $0.25, 30 LLM calls, 5 minutes), exposed to Dev's settings UI.
- [ ] 4. Tests for cost math and budget enforcement.

**Done when:** the UI model dropdown is filled from `/v2/models` and budgets stop a runaway run.

---

## A-11 · Search and fetch tools

**Owner** AI · **Size** M (1.5 days) · **Priority** P1 · **Depends on** D-13

**Steps**
- [ ] 1. `SearchProvider` interface. Ship `ddgs` (no key) and one keyed provider (Brave, Tavily or SearXNG). Failures raise `ToolError`; **never** return fake results.
- [ ] 2. `web_fetch`: uses Dev's SSRF-safe client, extracts the main text (for example trafilatura or readability-lxml; check licenses before you ever distribute), caps at 8,000 characters, returns title and URL, wrapped as untrusted (A-09).
- [ ] 3. Recorded-response tests, plus a live check with a research agent.

**Done when:** a research agent returns real, cited results, and a missing key gives an actionable error.

---

# Milestone 3: Installable app

## A-12 · Starter agent templates

**Owner** AI · **Size** M (1.5 days) · **Priority** P1 · **Depends on** S-04

**Steps**
- [ ] 1. Three JSON templates with tuned prompts and budgets: Research assistant (lead, searcher, writer), Code reviewer, Daily planner (single agent, memory on).
- [ ] 2. `scripts/seed_templates.py` creates them through the API (uses the token).
- [ ] 3. Run each 5 times; record results in the evals.

**Done when:** all three run cleanly in the installed app.

## A-13 · Usage data spec

**Owner** AI · **Size** S (0.5 day) · **Priority** P2 · **Depends on** A-10

Write `docs/USAGE.md`: what the usage UI shows (per run, agent, model, day), the `totals` fields, and how unknown prices are shown. Dev builds D-21 from it.

## A-14 · Real-world tuning

**Owner** AI · **Size** L (3 days) · **Priority** P0 · **Depends on** D-19

**Steps**
- [ ] 1. Run the M3 acceptance scenarios on the **installed** app with real models.
- [ ] 2. Tune `max_iterations`, `max_depth`, `max_result_chars`, model tiers and prompt wording.
- [ ] 3. Write `docs/TUNING.md` with the final defaults and why.

**Done when:** acceptance passes (S-05).

---

## After M3 (AI side, outline only)

Use M3 slack for spikes: retrieval memory (SQLite FTS5, then local embeddings), an "improve this agent" action that proposes a prompt diff from failed traces for you to approve, an MCP client, token streaming, structured outputs and typed handoffs between agents, local models (Ollama). Detailed cards get written at the M3 gate.
