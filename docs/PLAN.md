# AgentForge: Collaboration Plan (revised)

Read in this order: **PLAN.md** (this file: decisions, rules, milestones) → **CONTRACTS.md** (the interfaces you both code against) → **MEMORY.md** (the memory architecture, v2) → your own task file: **TASKS-DEV.md** or **TASKS-AI.md**.

Roles: **Dev** = the developer (platform, UI, safety, packaging). **AI** = the AI lead (agent core, prompts, memory, evals). Replace the labels with your names. Date: 2026-10-01, **revised 2026-10-06**.

## What changed in this revision

- **Memory is now a full architecture, built in one effort** (new `MEMORY.md`): semantic memory, hybrid search, conversation compaction, episodic recall of past runs, standing intents (reminders) and idle "dreams". ADR-002 records the decision.
- **New milestone M2b · Memory** between M2 and M3. M2 keeps its meaning (safe and solid) and no longer waits for memory. Cards A-06 and D-16 are replaced by A-06a to A-06g and D-16a to D-16e (section 6b). A-07 (lessons) moves to M2b.
- **Memory contracts go into contracts v1** (S-02), so the Runner interface is not reopened later.
- **Ollama is a first-class backend from M1**, not a post-M3 spike (section 2b).
- **Large inputs and core tools** (section 6c, ADR-003): image support, structured output and reasoning in the contracts and LLM types, saving big tool results, in-run context trimming, and new core tools (`plan`, `summarize`, `doc_search`, `analyze_image`). Sub-agent memory rule in MEMORY.md section 2b.
- **Effort:** AI about 44 focused days in total (was 30), Dev about 41 (was 34.5).

---

## 1. Decisions

### ADR-001: rewrite the core in place, do not restart the project

**Status:** proposed (accept it in S-01). **Deciders:** Dev, AI.

**Context.** The code review found the real problems in one place: the agent "brain". That is the loop and LLM layer (`app/llm.py`, `app/runtime/agent.py`), the event and trace model (`engine.py`, `useExecutionStream.ts`, `ExecutionTree.tsx`) and memory (`memory.py`, learned experience). Roughly 1,000 of about 6,500 lines, so about one-seventh (my estimate). Everything else (Electron shell, UI, API, database, graph validation, tools) works and needs fixing, not replacing. Goal: personal use first, an installable app later.

| | A. Restart in a new repo | B. Fix everything in place | C. Rewrite the core in place |
|---|---|---|---|
| Effort | about 4 to 6 focused weeks just to get back to today's features (estimate) | lowest | about 10 to 12 focused days for the new core (A-02, A-03, A-04) |
| Risk | rebuilding plumbing, repeating the same design mistakes, nothing usable for weeks | patching a loop built on string tags; AI works in code they do not want to own | two engines coexist for a while (mitigated by a flag, a freeze and deletion in S-04) |
| Team fit | AI gets total control; Dev redoes work that already exists | fine for Dev, poor for AI | AI owns a greenfield module; Dev owns the platform |

**Decision: C.** AI builds a new `app/core/` behind the `Runner` interface (the fresh start, where it counts). Dev fixes and hardens the platform and builds a FakeRunner so the UI never waits. The old engine is frozen and deleted in S-04.

**Consequences.** Contracts must be agreed first (S-02). Temporary duplication of the engine. The 45 video tools are parked behind a switch.

**Revisit when** (a full restart becomes right): the product changes shape (cloud, multi-user, mobile, a TypeScript-only runtime), you adopt a framework that dictates the structure, or either of you will not maintain this codebase. If so, use Appendix A: the cards still apply.

### ADR-002: build the full memory architecture in one effort

**Status:** accepted 2026-10-06. **Details:** `MEMORY.md`.

**Decision.** Ship all layers together, each behind its own switch: semantic memory with FTS5 and Ollama embeddings, conversation compaction, episodic recall (`<recent_runs>`, `recall_run`), standing intents (reminders), and dreams (suggestions that need your Accept). The risky parts (intents, dreams, embeddings) are **off by default**.

**Accepted answers to the open questions:**
- **M1:** memory extraction runs **inline** at the end of a run, counted in run totals. A setting `extraction_mode: inline | background` exists in case local-model latency makes it annoying.
- **M2:** limits stay as proposed (500 memories per agent, 800 recall tokens, 20 active reminders, 3 auto-runs a day, $0.10 per auto-run). All are settings.
- **M3:** embeddings **off by default**; with Ollama detected, settings offers a one-click enable.
- **M4:** `auto_run` reminders **ship, off by default**; only the user can enable them, per reminder, in the UI.

**Consequences.** M2 splits into M2 and M2b; the memory contracts are frozen in S-02; about 8.5 extra AI days and 5.5 extra Dev days.

### ADR-003: large inputs are handled by handles and small pieces

**Status:** accepted 2026-10-06. **Details:** section 6c.

**Decision.** Never put a whole large file, codebase, image or video in the prompt. Tools return small pieces (ranges, search hits, summaries, downscaled images) and the agent keeps handles (workspace paths, artifact ids). Tool results that are too long are saved to the workspace and replaced by a head plus a pointer; old results can be stubbed out mid-run.

**Consequences.** The reasoning, pagination, attachment and alias shapes join contracts v1 (S-02); image parts and `response_format` are documented in C-7 (AI-owned). A-02, A-03, A-04, A-08 grow; D-08 and D-09 grow slightly; new cards A-15a to A-15c.

---

## 2. Scope for personal use

- **Build now:** create agent teams in the UI, chat, watch a live and correct trace (including tool calls), Stop a run, see cost, optional memory with reminders and suggestions, lessons, safe tools, an installer for your own OS.
- **Not now:** public release, code signing and notarization, auto-update, multi-user or cloud, cloud-shared memory, i18n, analytics, polishing the video pack.
- **Always keep, even for personal use:** the local API token (any web page can reach `localhost`), workspace-scoped tools, approvals for `python` and `http_request`, key protection, database integrity, tests and CI, per-run budgets.

### 2b. Local models with Ollama

You run Ollama, so these points are planned for instead of discovered late:

1. **Tool calling.** Pick a chat model that supports tool calling (check the model's page in the Ollama library for the `tools` tag). Record the choice in `docs/FIRST_RUN_NOTES.md` in S-01; A-02's live test proves it.
2. **Context window.** Ollama's default context window is small and has changed between versions (check yours). Set it explicitly per model (`num_ctx` in `models.yaml`); compaction (A-06c) reads the window from there. A larger window needs more RAM or VRAM.
3. **Embeddings.** Pull an embedding model (for example `nomic-embed-text`) and set it as `embedding_model`. Because it is local, memory text never leaves your machine through embeddings.
4. **Budgets.** Local runs cost $0, so the real limits are LLM calls, tokens and seconds. The default time limit is raised for local models (suggest 10 minutes) in A-10. Pricing for local models is an explicit `0.0`, not "unknown".
5. **Reliability.** Small models are weaker at strict JSON and tool calls. Memory calls use Ollama's structured output (JSON schema) where the model supports it, and validation stays deterministic, so bad output means nothing is written. Use the `fast` alias for extraction and dreams. Run the live evals with your Ollama model.
6. **Latency.** Inline extraction may add seconds with a local model. If the median is above about 5 seconds, switch `extraction_mode` to `background`.
7. **System check (D-15).** Verify Ollama answers at its URL and that the chat and embedding models are pulled.
8. **Not a conflict with SSRF rules.** The `http_request` block on `localhost` applies to the agent's tool, not to the LLM backend that talks to Ollama.
9. **Vision.** `analyze_image` (A-15b) needs a vision-capable model, set as `vision_model`. Pull one (check the Ollama library for the vision tag) and keep `num_ctx` large enough for image input. If none is configured the tool reports a clear error and the rest of the app is unaffected.

---

## 3. Roles and ownership

| Path | Owner | Notes |
|---|---|---|
| `electron/**`, `src/**`, `package.json`, `vite.config.ts`, `index.html`, `tailwind.config.js` | Dev | |
| `python-runtime/main.py`, `app/{db,models,schemas}.py`, `app/routers/**`, `app/services/**`, `app/infra/**`, `app/dev/**`, `alembic/**`, `python-runtime.spec`, `.github/**`, `scripts/**` | Dev | |
| `app/tools/**` | Dev for structure and safety | AI edits only `Input` models, descriptions and error messages (A-05), in separate small PRs |
| `app/core/**`, `app/prompts/**`, `evals/**` | AI | `app/core/` never imports SQLAlchemy or FastAPI |
| `app/contracts/**`, `src/contracts.ts`, `docs/CONTRACTS.md`, `docs/MEMORY.md` | Shared | PR labelled `contract`, both approve |
| `app/llm.py`, `app/runtime/**`, `spike/**` | Frozen legacy | bug fixes only where a card says so; deleted in S-04 |
| `docs/**`, `tests/**` | Shared | |

Target layout after M2b:

```
python-runtime/
  main.py
  app/
    contracts/   shared: pure types (incl. memory, intents, insights, run history)
    core/        AI: llm/, runner.py, budget.py, spans.py, prompts/, memory/, lessons/, tools/, cli.py
                 memory/: recall, extractor, safety, compaction, embedder, intents, episodic, dream, inmemory
                 tools/: plan, summarize, doc_search, analyze_image (A-15)
    infra/       Dev: paths, auth, workspace, approvals, ssrf
    services/    Dev: executions.py, graph_loader.py, memory_store.py, run_history.py,
                 intent_scheduler.py, dream_scheduler.py, notifications.py
    routers/     Dev: ..., executions_v2.py, conversations.py, system.py, memory.py, intents.py, insights.py
    tools/       Dev structure; AI schemas
    dev/         Dev: fake_runner.py, scenarios/
  evals/         AI
  tests/         both
src/             Dev (contracts.ts shared)
docs/            PLAN, CONTRACTS, MEMORY, TASKS-*, DECISIONS, SMOKE, TOOL-WRITING, TUNING
```

---

## 4. Working agreement

1. `main` always runs. Nobody pushes straight to `main`.
2. One task = one branch (`dev/D-04-run-lifecycle`, `ai/A-03-runner`) = one PR. Keep PRs under about 500 changed lines; split if bigger. The PR title starts with the task ID.
3. The other person reviews within 2 days, checking the card's "Done when" list. Squash merge.
4. Tick the boxes in the task file in the same PR.
5. Contracts change only through a `contract` PR approved by both.
6. Live LLM tests are marked `live`, run by hand, use your local Ollama model or a cheap cloud model, and a hard budget. CI never spends money and never needs Ollama.
7. Never commit keys. Tests use fake keys.
8. Blocked for more than a day, or a card is unclear or wrong: say so and fix the card in a PR.
9. Two 30-minute syncs a week; a short demo at every milestone gate. Record decisions in `docs/DECISIONS.md`.

**Definition of done (every task):** merged via a reviewed PR; every "Done when" box ticked; tests added or updated and CI green; docs updated if behavior, config or a contract changed; no new `except Exception: pass`; no new hard-coded ports or paths.

---

## 5. Milestones, gates and effort

Effort is in focused days (about 6 productive hours). Sizes and priorities are on each card.

**M0 · Ready to collaborate** (S-01, S-02). *Goal: both can run the app and the interfaces are frozen, including the memory contracts.*
Gate: both chat with an agent locally (with your Ollama model); `docs/` merged; contracts v1 tagged.

**M1 · Stable core** *Goal: a chat message runs through a new, correct loop and every step, including tool calls, shows in a correct live tree.*
- Dev (14d): D-01 quick wins, D-02 tests and CI, D-03 database, D-04 run API, D-05 FakeRunner, D-06 run tree UI, D-07 chat v2, D-08 tool v2 base (2.5d, with a pagination convention and a workspace write call).
- AI (14.5d): A-01 decision, A-02 LLM adapter (Ollama, images, structured output, reasoning; 4.5d), A-03 Runner (with saved tool results and in-run trimming; 5.5d), A-04 prompts (2d), A-05 tool schemas.
- Shared: S-03 integration day.
- Gate, all seven pass with `AGENTFORGE_RUNNER=v2`: (1) fresh data folder, first agent created and last agent deleted without a crash; (2) one agent with one tool shows agent, llm_call, tool_call, llm_call, and the answer has a usage line; (3) CEO → Research → web_search nests correctly, CEO shows completed, Research appears once; (4) a failing tool does not kill the run; (5) Stop ends the run in about 2 seconds with all spans closed; (6) kill the backend mid-run, restart: the run shows `interrupted`. Scenarios 2 and 3 also pass with your Ollama model. (7) a 50,000-character tool result is saved to the workspace and the model sees the head plus a pointer; a scripted tool-heavy run stays under the context window through in-run trimming.

**M2 · Safe and solid** *Goal: safe to leave running on your own machine; evals guard the core; legacy code is gone.*
- Dev (11.5d): D-09 to D-15 (D-09 grows to 3d: paginated read, grep and stat file tools).
- AI (8.5d): A-08 to A-11 and A-15a (A-08 grows to 3.5d with large-input evals; A-10 grows to 2d for Ollama entries; A-15a is the `plan` tool, 0.5d).
- Shared: S-04 cut-over.
- Gate: (1) no token gives 401 and another origin cannot call the API; (2) tools cannot write outside the run workspace (tests with `../` and absolute paths); (3) `python` and `http_request` pause for approval, Deny reaches the model as a tool error; (4) `http_request` to localhost, `169.254.169.254` and private ranges is refused; (5) offline evals run in CI and pass, including injection; (6) legacy code deleted (the `learned_experience` column stays until A-07 migrates it); (7) a large-file eval passes: the agent finds a fact deep in a 5 MB text file using paginated reads and search, without loading the whole file.

**M2b · Memory** *Goal: the full memory architecture works, is visible and editable, and fails safely.*
- Dev (7d): D-16a to D-16e.
- AI (16d): A-06a to A-06g (10.5d), A-07 lessons (3d) and A-15b core tools for large inputs (2.5d).
- Shared: S-06 memory integration.
- Dev slack (about 6 days): start M3 cards D-17 and D-18 early (they depend only on S-04), or help with eval fixtures.
- Gate, with Ollama for chat and embeddings: (1) memory is opt-in per agent; state a preference, start a new chat, it is recalled; it shows in the UI with its evidence, and edit, delete and Markdown export work; (2) a failed extraction, compaction, embedding or dream writes nothing and the run still completes; (3) with Ollama embeddings on, a paraphrased query finds the right memory, and with Ollama stopped recall falls back to keyword search without an error; (4) a long chat is compacted and a planted fact survives; (5) a failed run appears in the next run's `<recent_runs>`, and an injected instruction inside an error message is not followed; (6) a reminder: the agent asks, you approve, it fires; Deny creates nothing; an agent cannot create an `auto_run`; an `auto_run` you enabled respects the daily cap, the budget and approvals; (7) a dream produces a suggestion you can accept or dismiss, nothing reaches a prompt before Accept, and background cost is visible; (8) poisoning evals (a tool result tries to create a memory or a reminder) pass in CI, and lessons are opt-in and versioned; (9) a 30-run simulation stays under the recall budget with every item findable; (10) large inputs: `summarize` condenses a large file and keeps a planted fact, `doc_search` finds a function in a codebase from a description, and `analyze_image` answers a question about a large image after downscaling.

**M3 · Installable app** *Goal: install it like a normal app on your own machine, with cost visible.*
- Dev (8.5d): D-17 to D-21.
- AI (5d): A-12 to A-14, then spikes with the slack.
- Shared: S-05 acceptance.
- Gate: (1) installer builds on your OS and installs on a clean user account or VM; (2) data lives in the OS user-data folder and survives a reinstall; (3) quitting leaves no Python process, and starting twice focuses the first window; (4) no external network requests at startup; (5) System check is green or shows clear fixes (including Ollama); (6) cost visible per run and per project; (7) the three starter templates run; (8) a 5-run soak with no crash.

**Totals:** AI about 44 focused days (14.5 + 8.5 + 16 + 5); Dev about 41 (14 + 11.5 + 7 + 8.5).

**Capacity worksheet** (plan to 75 percent of your time, as buffer): `focused days per week = hours per week × 0.75 ÷ 6`, and `weeks = milestone days ÷ focused days per week`. Example for AI's M2b (16 days): at 10 h/week about 13 weeks, at 20 h/week about 6.5 weeks, at 40 h/week about 3 weeks. If that feels too long, cut P1 and P2 cards, not quality; the order inside M2b (section 6b) lets you stop after any card and still have something that works. Fill in your real hours before you start.

**First 10 focused days**
- Dev: S-01 → D-01 → D-02 → S-02 → D-03 → D-04 → start D-05.
- AI: S-01 → A-01 → S-02 → A-02 (Ollama backend first) → start A-03.
- Both, end of M1: run D-19 step 0 (one unchanged `npm run dist`, only to learn what breaks).

**Dependencies (simplified)**
```
S-01 -> S-02 -+-> D-03 -> D-04 -> D-05 -> D-06, D-07 --+
              +-> D-08 --------------------------------+-> S-03 (end M1)
              +-> A-02 -> A-03 (A-04 in parallel) -----+
A-01 -> A-02          A-05 needs D-08          D-01, D-02, A-01 can start on day 1

M2:  D-09..D-15, A-08..A-11, A-15a  ->  S-04
M2b: A-06a -> A-06b, A-06c, A-06d, A-06e -> A-06f (needs D-12) -> A-06g ; A-07 after A-06b
     D-16a -> D-16b -> D-16c (needs D-12) -> D-16d -> D-16e          ->  S-06
     A-15b needs A-06d and image support in A-02                                ->  S-06
M3:  D-17, D-18 may start after S-04; A-12 needs M2b
```

---

## 6. Shared tasks

### S-01 · Repo setup and first run (both, half a day, M0, P0)
- [ ] 1. Decide access: AI adds Dev as a collaborator (GitHub → Settings → Collaborators), or Dev forks. Pick one and write it here.
- [ ] 2. Both install Git, Node 20+, `uv`, optionally ffmpeg. The person using Ollama installs it, pulls a **tool-calling chat model** and an **embedding model**, and notes both in `docs/FIRST_RUN_NOTES.md`.
- [ ] 3. Clone, `npm install`. Backend: `cd python-runtime && uv python install 3.11 && uv venv --python 3.11 && uv sync && uv run python main.py`; open `http://127.0.0.1:8000/health` (the README says 8756: wrong).
- [ ] 4. Frontend: `npm run dev`. If Electron cannot start its own Python (dev mode spawns bare `python3`), keep step 3 running in another terminal; the app connects to port 8000 either way (fixed in D-18).
- [ ] 5. In the app: pick a provider (a cloud key in Settings, or Ollama), create an agent, Config → pick provider and model, chat "hello".
- [ ] 6. Write every problem into `docs/FIRST_RUN_NOTES.md`.
- [ ] 7. Copy these files into `docs/` (PLAN, CONTRACTS, MEMORY, TASKS-DEV, TASKS-AI), add `docs/DECISIONS.md` (Appendix B). PR `shared/S-01-docs`, other person approves.
- **Done when:** both can chat with an agent locally, `docs/` is on `main`, ADR-001 to ADR-003 are accepted or changed.

### S-02 · Contracts session (both, 2 hours plus one day for Dev, M0, P0)
- [ ] 1. Both read `CONTRACTS.md` and `MEMORY.md` section 3 beforehand and comment on anything unclear.
- [ ] 2. Walk C-1 to C-9 **with the memory changes applied**: C-6 replaced by the memory, run-history, intent and insight contracts (MEMORY.md 3.1 to 3.4); `RunRequest`, `RunResult`, `RunOptions` and `Runner.run` extended (3.5), **and the large-input shapes from section 6c**: `reasoning` in `LLMParams`, `truncated` and `next_offset` on `ToolResult`, `attachments` on `RunRequest`, `llm_aliases` on `RunOptions`, and `lessons`, `intents`, `run_history`, `clock` on `Runner.run`. Image content parts and `response_format` live in the AI-owned LLM types (C-7): they are documented in `CONTRACTS.md` but not frozen in `contracts/`. AI asks "can the core do everything it needs with these shapes?" Dev asks "can the UI, database and API render, store and replay this?"
- [ ] 3. Answer Q1 to Q8 inline in `CONTRACTS.md` (tick each box); Q9 to Q12 (= memory M1 to M4) are already answered by ADR-002; answer the new Q13 to Q15 (attachments, `llm_aliases`, `lessons` in `Runner.run`).
- [ ] 4. Dev reviews and merges the drafted `contracts-v1` files: `app/contracts/` (`run`, `events`, `tools`, `naming`, `graph`, `runner`, `memory`, `api`, `checks`), `src/contracts.ts` and `tests/test_contracts.py`. The test builds the example event sequence from C-2 and checks R1 to R6 and S1 to S4; `checks.py` is reused by D-05 and A-03. Run `uv run pytest` to confirm with the real pydantic.
- [ ] 5. PR labelled `contract`, AI approves, tag `contracts-v1`.
- **Done when:** merged, test green, Q1 to Q15 answered, both agree the contracts are frozen. Memory is not implemented yet; M0 only freezes its shapes.

### S-03 · Integration day #1 (both, 1 day, end of M1, P0)
- [ ] 1. Add `AGENTFORGE_RUNNER=fake|v2` in `services/executions.py`; AI provides `core.runner.build_runner()`.
- [ ] 2. Together wire `graph`, `tools` (LegacyToolAdapter), `workspace` (temp dir), `approvals` (auto-allow) into `Runner.run`, and **no-op** `memory`, `intents` and `run_history` (the protocols exist from contracts v1).
- [ ] 3. Run the seven M1 gate scenarios with FakeLLM, then with your Ollama model.
- [ ] 4. Compare the live trace with the FakeRunner scenario. Fix code, not contracts (if a contract must change, use a `contract` PR).
- [ ] 5. Switch the UI default to `engine = v2`. Write findings in `docs/INTEGRATION-1.md`.
- **Done when:** all seven scenarios pass on `v2`.

### S-04 · Cut-over and delete legacy (both, 1 day, end of M2, P0)
- [ ] 1. Make v2 the only path; remove the flag and the developer toggle.
- [ ] 2. Delete `app/llm.py`, `app/runtime/`, `spike/` (keep `headless_spike.py` under `docs/history/` if you like), the old `/executions` routes, `useExecutionStream.ts`, the old `ExecutionTree.tsx`, `workspace_from()`, the `/files` legacy route, and the old `memory.py` and learned-experience code paths. **Keep the `learned_experience` database column** until A-07 migrates it.
- [ ] 3. Update the README (architecture with `core/`, how to run, links to `docs/`). Tag `v0.2-core`.
- **Done when:** `grep -rn "runtime.agent\|app.llm" python-runtime` finds nothing and CI is green.

### S-05 · Personal-use acceptance (both, 1 day, end of M3, P0)
- [ ] Run `docs/SMOKE.md` and the M3 gate list on the installed build. Fix P0 defects. Tag `v0.3-personal`.

### S-06 · Memory integration (both, 1 day, end of M2b, P0)
- [ ] 1. Replace the no-op `memory`, `intents` and `run_history` with the real stores in `services/executions.py`; start the intent and dream schedulers.
- [ ] 2. Run the ten M2b gate scenarios with FakeLLM and FakeEmbedder, then by hand with Ollama (chat and embeddings).
- [ ] 3. Check the sizes in practice: prompt overhead of the memory blocks, extraction latency (decide `inline` or `background`), recall quality on your real notes.
- [ ] 4. Write findings in `docs/INTEGRATION-2.md`. Tag `v0.2-memory`.
- **Done when:** all ten M2b gate items pass.

---

## 6b. Memory work package (M2b)

Details live in `MEMORY.md`; section numbers below point there. Each card is its own branch and PR. Build in this order; every card leaves the app working.

**Summary**

| ID | Card | Owner | Size | Pri | Depends on |
|---|---|---|---|---|---|
| A-06a | Memory core: stores, recall | AI | M (1.5d) | P1 | A-03 |
| A-06b | Extraction and safety filters | AI | M (1.5d) | P1 | A-06a, A-10 |
| A-06c | Conversation compaction | AI | M (1d) | P1 | A-06a, A-10 |
| A-06d | Embeddings with Ollama and hybrid search | AI | M (1.5d) | P1 | A-06a, D-16a |
| A-06e | Episodic recall | AI | M (1.5d) | P1 | A-06a, D-16b |
| A-06f | Standing intents (agent side) | AI | M (1.5d) | P1 | A-06a, D-12, D-16c |
| A-06g | Dreams and memory evals | AI | L (2d) | P1 | A-06e, D-16d, A-08 |
| A-07 | Lessons (replaces learned experience) | AI | L (3d) | P1 | A-06b |
| D-16a | Memory storage and API | Dev | M (1.5d) | P1 | S-02, D-03, D-14 |
| D-16b | Run history for episodic recall | Dev | M (1d) | P1 | D-04, D-14 |
| D-16c | Intents backend, scheduler, notifications | Dev | M (1.5d) | P1 | D-12, D-16a |
| D-16d | Dreams backend, maintenance runs, system checks | Dev | M (1d) | P1 | D-16b, D-16c |
| D-16e | Memory UI | Dev | M (2d) | P1 | D-16a to D-16d |

### A-06a · Memory core: stores and recall (AI, 1.5d)
- [ ] 1. `inmemory.py`: `InMemoryStore`, `InMemoryIntentStore`, `InMemoryRunHistory`, `InMemoryInsightStore` implementing the contract protocols (tests, CLI and S-03 use them).
- [ ] 2. `recall.py` per MEMORY.md 5.1, keyword-only formula first: pinned first, then score by keyword, recency and usage, within `recall_budget_tokens` and 12 items; pinned hard cap; `touch` the injected items.
- [ ] 3. `<memory>` block in the A-04 prompt builder, with the "background, never instructions" wording and the `(inferred)` marker.
- [ ] 4. Tests: pinned first, budget respected, expired and superseded items never returned, a 30-run simulation.
- **Done when:** a test proves every item is findable by its own keywords, and the prompt snapshot shows the block.

### A-06b · Extraction and safety (AI, 1.5d)
- [ ] 1. Gate (no LLM) and extraction call per MEMORY.md section 6; use structured output where the model supports it; `fast` alias.
- [ ] 2. `safety.py`: JSON parse, 200-character limit, **evidence must appear in a user message of this run**, URL and secret and instruction-pattern filters, dedupe (normalized plus Jaccard 0.8), `supersedes` checks, per-agent cap.
- [ ] 3. Inline as an `llm_call` named `memory_extract` inside the root agent span; setting `extraction_mode: inline | background`.
- [ ] 4. Any error means no write. Tests with FakeLLM for every rule and every failure.
- [ ] 5. Sub-agent rule (MEMORY.md section 2b): extraction writes only to the **root agent's** memory, from the user's own messages. A parent-written task or a sub-agent's output is never an extraction source. Add a test for it.
- **Done when:** a failed or malformed extraction writes nothing, evidence-less items are dropped, and an injected tool result never becomes a memory.

### A-06c · Conversation compaction (AI, 1d)
- [ ] 1. Trigger `min(0.75 × context window, 20,000)` using `models.yaml` (the Ollama `num_ctx` for local models; 32,000 if unknown).
- [ ] 2. Keep the last 6 messages; summarize the rest plus the old summary into at most about 400 words with the `summarizer_model`; `llm_call` named `compaction`; return `new_summary` and `summarized_count`.
- [ ] 3. `<conversation_summary>` block; failure fallback (`[earlier messages omitted]`, no `new_summary`).
- [ ] 4. Tests: threshold, planted fact survives, fallback.
- **Done when:** a long scripted chat stays under the window and the planted fact is still answerable.

### A-06d · Embeddings with Ollama and hybrid search (AI, 1.5d)
- [ ] 1. `Embedder` interface; providers: Ollama (and any OpenAI-compatible endpoint); `kind: embedding` entries in `models.yaml`; `embed` spans.
- [ ] 2. Embed the query once per run (cached) and the new memories in one batched call; failures fall back to keyword-only and never fail a run or block a write.
- [ ] 3. Hybrid scoring from MEMORY.md 5.1 (similarity below 0.25 counts as 0); only items whose `embedding_model` matches take part.
- [ ] 4. `embed_backfill` function for Dev's maintenance job (`missing_embeddings`, `set_embeddings`).
- [ ] 5. Tests with a deterministic FakeEmbedder; one `live` test with your Ollama embedding model.
- **Done when:** a paraphrase test beats keyword-only, a model change does not break recall, and Ollama stopped means keyword fallback without an error.

### A-06e · Episodic recall (AI, 1.5d)
- [ ] 1. `<recent_runs>` builder: root agent only, problems in the last 48 hours, at most 3 runs and 300 tokens, marked untrusted.
- [ ] 2. `recall_run(query, limit)` read-only tool, result wrapped as untrusted (A-09).
- [ ] 3. Tests, including an error message that contains an instruction: the FakeLLM obeys it, the guard catches it.
- **Done when:** a failed run shows up in the next run's prompt and no instruction inside it is followed.

### A-06f · Standing intents, agent side (AI, 1.5d)
- [ ] 1. Tools `intent_create`, `intent_list`, `intent_cancel` per MEMORY.md section 10: quote required, text filters, 20-intent cap, **forced approval** for create and cancel, always `mode="remind"`.
- [ ] 2. Current date, time and timezone in the prompt; a `Clock` you can fake; resolve `when` to UTC.
- [ ] 3. `<reminders>` block from `due_for_run`, then `mark_fired`.
- [ ] 4. Tests with a fake clock: no evidence, denied approval, injected request, caps, daily and weekly repeat.
- **Done when:** the agent can never create an intent without a user approval, and cannot create an `auto_run`.

### A-06g · Dreams and memory evals (AI, 2d)
- [ ] 1. `dream.py` per MEMORY.md section 11: input is run digests and memory titles only; 2 calls and $0.10 maximum; at most 3 insights; cited execution ids must exist; the filters from A-06b.
- [ ] 2. Eval tasks in the A-08 format: memory recall, memory poisoning, reminder poisoning, contradiction (supersede), compaction fact survival, dream gating and validation.
- [ ] 3. Wire the offline evals into CI.
- **Done when:** invalid dream output writes nothing, and all memory evals run offline in CI.

### D-16a · Memory storage and API (Dev, 1.5d)
- [ ] 1. Alembic migration (MEMORY.md section 4): new `memory_entries` columns, `memory_fts` with triggers, `conversations.summary` and `summarized_count`.
- [ ] 2. `services/memory_store.py`: the SQL `MemoryStore` (FTS5 `candidates`, cosine over matching vectors, `related`, transactional `add` with supersede, `touch`, embedding backfill methods).
- [ ] 3. Routes under `/v2/memory` (list, search, edit, pin, delete, clear, export Markdown); store `new_summary` and send `history_summary` (with D-14).
- **Done when:** the contract tests pass against the SQL store as well as `InMemoryStore`.

### D-16b · Run history (Dev, 1d)
- [ ] 1. `executions_fts` and `executions.feedback` (if D-14 has not added it).
- [ ] 2. `services/run_history.py`: `search` and `recent(only_problems=True)` building `RunDigest` (errors cut to 200 characters).
- **Done when:** digests for failed, cancelled, budget-stopped and thumbs-down runs come back correctly.

### D-16c · Intents backend (Dev, 1.5d)
- [ ] 1. `SqlIntentStore`, `notifications` table and routes, `/v2/intents`.
- [ ] 2. `intent_scheduler.py`: 30-second loop; `remind` creates a notification; missed intents fire once at startup; repeats advance `due_at`.
- [ ] 3. `auto_run` (user-enabled only): start a normal run through the ExecutionManager with the reduced budget, a 2-minute approval timeout (then deny) and the daily cap.
- **Done when:** scheduler tests with a fake clock pass and an auto-run can never skip approvals.

### D-16d · Dreams backend and system checks (Dev, 1d)
- [ ] 1. `SqlInsightStore`; Accept writes an `inferred` memory in one transaction; routes `/v2/insights`.
- [ ] 2. `dream_scheduler.py`: idle for `dream_idle_minutes`, 5 or more new runs, once a day, project switch `dreams_enabled`.
- [ ] 3. `maintenance_runs` rows (dream, embed_backfill) with status and cost; schedule the backfill when the embedding model changes.
- [ ] 4. D-15 additions: FTS5 present, Ollama reachable, chat and embedding models pulled.
- **Done when:** a dream and a backfill each leave a `maintenance_runs` row, and failures show up as notifications.

### D-16e · Memory UI (Dev, 2d)
- [ ] 1. Memory list (search, badges, evidence, `last_used_at`, `use_count`, edit, pin, delete, clear all, export) and the per-agent toggle.
- [ ] 2. Reminders screen (create, cancel, repeat, **auto-run toggle**) and the Suggestions screen (Accept, Dismiss, evidence links).
- [ ] 3. Notification inbox and toasts; Background activity list with cost; project settings for episodic, reminders, dreams, embedding model (with the Ollama one-click enable), recall budget, caps, auto-run limits and `extraction_mode`, each with a one-line explanation and where data goes.
- [ ] 4. Banners: item cap reached, pinned over budget, history summarized. Lessons UI from the old D-16 (list, history, enable) is included here.
- **Done when:** the memory gate items (1 to 9) can be demonstrated entirely from the UI.

---

## 6c. Large inputs and core tools

**Rule (ADR-003):** never put a whole large file, codebase, image or video in the prompt. Tools return small pieces and the agent keeps handles (workspace paths, artifact ids).

**Summary**

| ID | Card | Owner | Size | Pri | Milestone | Depends on |
|---|---|---|---|---|---|---|
| A-02 | + images, `response_format`, `reasoning` | AI | +0.5d (now 4.5d) | P0 | M1 | S-02 |
| A-03 | + saved tool results, in-run trimming, retry on context overflow | AI | +1d (now 5.5d) | P0 | M1 | A-02 |
| A-04 | + planning, self-check and large-input guidance, `<plan>` block | AI | +0.5d (now 2d) | P0 | M1 | A-02 |
| A-08 | + large-file, codebase and image eval tasks | AI | +0.5d (now 3.5d) | P0 | M2 | A-03 |
| D-08 | + pagination convention, workspace write call | Dev | +0.5d (now 2.5d) | P0 | M1 | S-02 |
| D-09 | + paginated read, grep and stat file tools | Dev | +0.5d (now 3d) | P0 | M2 | D-08 |
| A-15a | `plan` tool | AI | S (0.5d) | P1 | M2 | A-03, A-04 |
| A-15b | `summarize`, `doc_search`, `analyze_image` | AI | L (2.5d) | P1 | M2b | A-02, A-06d |
| A-15c | `think`, `check_work` (optional, not in the totals) | AI | S (0.5d) | P2 | M3 slack | A-15a, A-08 |

### Additions to existing cards

**A-02 (AI)**
- [ ] Image content parts: a message part is `text` or `image`; an image is a workspace path, read and base64-encoded only at the backend edge. Events and logs never contain image bytes.
- [ ] `response_format` (JSON schema) passed through to the backend, so memory extraction and dreams can use Ollama structured output.
- [ ] `reasoning` param in `LLMParams`; thinking text is stored separately from `content`, kept out of the answer and out of replayed history.
- [ ] FakeLLM supports image parts and structured output; one `live` test with your vision model.

**A-03 (AI)**
- [ ] Save results: every tool result over 1,000 characters is also written through `ctx.workspace` to `.results/<tool_call_id>.txt` (an `ArtifactRef` on the span). The model sees it in full up to `max_result_chars`; above that it sees the head plus `…[truncated N chars; full result saved at <path>; read a range or search it]`.
- [ ] In-run trimming: when the run's messages pass about 70 percent of the context window, replace the oldest tool results (keep the latest 3) with stubs pointing to their saved files. If still too large, summarize older messages with the `summarizer_model` as an `llm_call` named `trim_summary`.
- [ ] On `LLMContextTooLong`: trim and retry once.
- [ ] Tests: a 50,000-character result, a long tool-heavy run stays under the window, the retry path, saved files cleaned with the workspace.

**A-04 (AI)**
- [ ] Planning: for tasks with 3 or more steps, write a plan first and update it as steps finish.
- [ ] Self-check: before the final answer, check the result against the task (re-read the output, run tests when available).
- [ ] Large inputs: never read a whole large file; use ranges and search; keep notes in the plan or a workspace file.
- [ ] `<plan>` block in the volatile section; update the prompt snapshots.

**A-08 (AI):** add three eval tasks: a fact deep in a large file (M2), a function found in a codebase (M2b), a question about an image (M2b).

**D-08 (Dev)**
- [ ] Pagination convention: tools that can return long output accept `offset` and `limit` and set `truncated` and `next_offset` in `ToolResult`.
- [ ] `ToolContext.workspace.write_result(...)` saves a spilled result and returns an `ArtifactRef`.

**D-09 (Dev)**
- [ ] File tools: paginated read (line or page ranges), `grep` (ripgrep or a Python fallback) and `stat` (size, type, line count, page count), all workspace-scoped and covered by the escape tests.
- Later, with the video pack: ffmpeg and transcription primitives.

### A-15a · `plan` tool (AI, 0.5d, M2)
- [ ] 1. `plan(items: list[{text, status}])` replaces the list; statuses `todo | doing | done`; at most 20 items; kept per agent in run state. `ToolResult.data` carries the structured list so the UI can show it (no new event kind).
- [ ] 2. The current plan is injected as `<plan>` on every LLM call, so it survives in-run trimming and compaction.
- [ ] 3. Eval: a multi-step task where the plan is written, updated and completed.
- **Done when:** the plan shows in the trace and in the prompt snapshot, and survives a trimmed run.

### A-15b · Core tools for large inputs (AI, 2.5d, M2b)
- [ ] 1. `summarize(source, focus)`: source is a workspace path or a saved-result handle. Chunk (about 2,000 tokens, small overlap), summarize each chunk with the `summarizer_model` (each an `llm_call` under the tool span), merge. Honors the shared Budget; refuses with a clear error above a chunk cap (suggest 50).
- [ ] 2. `doc_search(source, query, limit)`: source is a file or a folder. Chunk text, and code by function or class where easy (else line windows); embed with the A-06d embedder (keyword-only fallback); in-memory index per run, cached by file hash; returns path, line range and snippet.
- [ ] 3. `analyze_image(path, question)`: downscale to a configurable maximum side (default 1,500 px), tile when the image is much larger or the question is about small text, send as an image part to the `vision_model`, return text. Size cap (suggest 20 MB).
- [ ] 4. Safety: all paths resolve through the workspace; results (including text read out of images) are wrapped untrusted (A-09).
- [ ] 5. Tests with FakeLLM, FakeEmbedder, a generated large file and image; a live test with your Ollama vision model.
- **Done when:** `summarize` keeps a planted fact in a 2 MB file, `doc_search` finds a function from a description, `analyze_image` answers about a downscaled image, and every call stays within budget.

### A-15c · `think` and `check_work` (AI, 0.5d, optional)
- [ ] `think(thought)`: no side effects, returns "ok", shows in the trace. Useful if your Ollama model has no native reasoning.
- [ ] `check_work(criteria)`: one cheap reviewer call over the draft the agent passes in; returns a list of issues; counts against the budget.
- [ ] Keep each tool only if the evals show a gain with your Ollama model; otherwise delete it.

---

## 7. After M3 (outline; detailed cards at the M3 gate)

- **AI-led:** "improve this agent" from failed traces, MCP client, streaming, typed handoffs, embeddings for run history, `analyze_video` (transcript plus frame captions; needs Dev's ffmpeg and transcription primitives), `ask_user` (pause a run for an answer; needs an approvals-style channel), a prompt-based tool-call fallback for models without native tool calling.
- **Dev-led:** project import and export, graph canvas, artifact browser, run comparison, accessibility.
- **Video pack (both, later):** a workflow (DAG) node type with artifact ids, local word-timing alignment, a sprite-based character rig with a per-frame compositor, QC that can really fail.
- **Not planned:** cloud-shared memory, multi-user scoping, free-form autonomous goals (only user-approved reminders exist).

---

## 8. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Contracts drift and integration hurts | Medium | High | `contract` PRs need both; memory shapes frozen in S-02; FakeRunner and FakeLLM keep both sides honest; S-03 is early |
| A-01 decision drags on | Medium | Medium | one-day time-box; default is a hand-rolled loop; interfaces do not change |
| Scope creep into the video pack | High | Medium | pack is off by default; only after M3 |
| Part-time availability slips | High | Medium | plan at 75 percent; P2 cards drop first; gates are scenario-based, not date-based; M2b cards are ordered so you can stop after any of them |
| Memory work delays the safe-core milestone | Medium | Medium | memory is its own milestone M2b; M2 does not wait for it |
| LLM cost during development and evals | Low | Low | FakeLLM in CI; local Ollama for live tests; per-run budget cap |
| Local-model weakness (JSON, tool calls, small context) | High | Medium | tool-calling model chosen in S-01; explicit `num_ctx`; structured output; deterministic validation; `extraction_mode` switch; live evals with your model |
| Large inputs overflow a small local context | High | Medium | save big results, in-run trimming, pagination, `summarize` and `doc_search` (section 6c); explicit `num_ctx` |
| No vision-capable model available locally | Medium | Low | `analyze_image` needs a `vision_model`; clear error if missing; everything else keeps working |
| Intents and auto-run abused through prompt injection | Medium | High | quote required, filters, forced approval for create and cancel, agents cannot set `auto_run`, daily cap, small budget, approvals still apply; poisoning evals in CI |
| Dreams cost time or compute in the background | Medium | Low | opt-in, idle-only, once a day, 2 calls maximum, suggestions only, `maintenance_runs` visibility |
| Packaging surprises (PyInstaller, LiteLLM) | High | Medium | early spike at the end of M1; fix in D-19; no bundled embedding model |
| Security regressions in tools | Medium | High | path-escape tests for every tool; approvals default to `ask` |
| One of you stops working in this codebase | Low | High | Appendix A (restart) reuses all cards |

---

## Appendix A: if you still prefer a fresh repo

- **Copy after reading:** `electron/`, build configs, `src/components/{AgentEditor,AgentTree,ToolLibrary,ToolCatalogModal,SettingsModal,TopBar}.tsx`, `src/store`, `src/api`, `app/graph.py`, `app/models.py` (apply D-03), `app/tools/*`, `alembic/`.
- **Do not copy:** `app/llm.py`, `app/runtime/*`, `useExecutionStream.ts`, `ExecutionTree.tsx`, the marker-based `AgentChat.tsx`, the learned-experience logic, `spike/`, the old README.
- **Order:** S-01, S-02 (contracts first, still, including memory), then repo skeleton with `contracts/`, FakeRunner, FakeLLM and CI (D-02), then follow the cards unchanged. D-01 disappears (you will not copy the buggy code) and D-03 becomes "create the schema".
- **Cost:** add roughly 1.5 to 2 focused weeks to rebuild shell, UI and API with no new capability. The memory cards (section 6b) are unchanged.

## Appendix B: `docs/DECISIONS.md` template

```
# Decision log

## D-1 (YYYY-MM-DD): <title>
Status: proposed | accepted | superseded by D-n
Context: why this came up
Decision: what we chose
Alternatives: what we rejected and why
Consequences / revisit when: ...
```
Reserved: **D-1** runner (hand-rolled vs library), **D-2** LLM backend (LiteLLM vs thin adapters; it must cover Ollama chat, tool calls, `num_ctx` and embeddings), both written in A-01. ADR-001 to ADR-003 above are the first accepted decisions.

## Appendix C: glossary

- **Sidecar:** the Python backend that Electron starts and talks to over local HTTP.
- **Runner:** the interface that runs one agent task and emits events (C-5). Real = `app/core/runner.py`, fake = `app/dev/fake_runner.py`.
- **Span:** one unit in the trace: an agent run, an LLM call or a tool call. Spans nest into a tree.
- **Contract:** a shared data shape in `CONTRACTS.md`; changing it needs both of you.
- **FakeLLM / FakeRunner / FakeEmbedder:** scripted stand-ins so you can build and test without a model, a key or the UI.
- **Workspace:** the per-run folder every tool must stay inside.
- **Legacy:** the old engine (`app/llm.py`, `app/runtime/*`), frozen until S-04.
- **Compaction:** summarizing older chat turns so a long conversation fits the context window.
- **Embedding:** a list of numbers that represents the meaning of a text, so search can match meaning, not just words.
- **Intent:** a user-approved reminder, due on the next run or at a set time.
- **Dream:** an idle-time analysis that proposes suggestions; nothing is used until you accept it.
- **Maintenance run:** a background job (dream, embedding backfill) recorded with status and cost.
- **Core tool:** a tool in `app/core/` that needs the runner, the LLM or the embedder (`plan`, `summarize`, `doc_search`, `analyze_image`, memory and reminder tools). Workspace tools (files, `python`, `http_request`) are Dev's.
- **Saved result:** a long tool result written to `.results/` in the workspace, replaced in the prompt by a head and a pointer.
- **In-run trimming:** replacing old tool results with stubs inside one long run. Not the same as compaction, which summarizes a conversation across runs.
- **Handle:** a workspace path or artifact id the agent holds instead of the content itself.
