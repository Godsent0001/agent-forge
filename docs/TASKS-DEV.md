# Tasks for Dev (platform, UI, safety, packaging)

You own everything that is not the agent "brain": Electron, React UI, FastAPI routes, database, tool infrastructure and safety, tests/CI and packaging. Read `PLAN.md` first (rules, ownership, milestones), then `CONTRACTS.md` (the interfaces you build against).

## How to use this file

- One card = one branch = one PR. Branch name example: `dev/D-04-run-lifecycle`.
- Work the steps in order and tick the boxes in the same PR.
- A card is **done** only when every "Done when" box is ticked, CI is green and AI has reviewed the PR.
- Sizes (focused days): **S** up to half a day, **M** 1 to 2 days, **L** 3 to 5 days. Priority: **P0** needed for the milestone gate, **P1** should, **P2** stretch.
- If a card is unclear or wrong, fix the card in a PR. These files are living documents.
- **Legacy** code (`app/llm.py`, `app/runtime/*`, old `/executions` routes) is frozen: only touch it where a card says so. It is deleted in S-04.

## What you need from AI, and when

| You need | From | When |
|---|---|---|
| Final shapes of events, tools and graph | S-02 (together) | end of M0 |
| The real `Runner` to replace the fake | A-03 | end of M1 (S-03) |
| `Input` models and descriptions for the general tools | A-05 | M1 to M2 |
| Memory and Lesson protocols and data shapes | A-06, A-07 | M2 |
| `models.yaml` and the registry behind `/v2/models` | A-10 | M2 |
| Starter templates (JSON) | A-12 | M3 |
| Usage fields and what the cost UI should show | A-13 | M3 |

## Summary

| ID | Card | Size | Pri | Milestone | Depends on |
|---|---|---|---|---|---|
| D-01 | Quick wins bundle | M (1d) | P0 | M1 | S-01 |
| D-02 | Tests and CI baseline | M (1d) | P0 | M1 | S-01 |
| D-03 | Database hardening and migrations | M (2d) | P0 | M1 | S-02 |
| D-04 | Run lifecycle API v2 | M (2d) | P0 | M1 | S-02, D-03 |
| D-05 | FakeRunner and scenarios | M (1d) | P0 | M1 | S-02, D-04 |
| D-06 | Run tree UI v2 | L (3d) | P0 | M1 | D-04, D-05 |
| D-07 | Chat v2 (history, Stop, usage) | M (1.5d) | P0 | M1 | D-04, D-05 |
| D-08 | Tool v2 base, registry, legacy adapter | M (2d) | P0 | M1 | S-02 |
| D-09 | Workspace path resolver, tool migration, video-pack toggle | L (2.5d) | P0 | M2 | D-08 |
| D-10 | API auth and CORS | M (1.5d) | P0 | M2 | D-04 |
| D-11 | API keys flow | M (1d) | P1 | M2 | D-10 |
| D-12 | Approvals and project settings | M (2d) | P0 | M2 | D-08, S-03 |
| D-13 | Python and HTTP tool safety | M (1.5d) | P0 | M2 | D-09 |
| D-14 | Conversations and run history | M (1.5d) | P1 | M2 | D-07 |
| D-15 | Dependencies and system check | M (1d) | P1 | M2 | D-09 |
| D-16 | Memory and lessons UI | M (1.5d) | P1 | M2 | A-06, A-07 |
| D-17 | Paths and data directory | M (1d) | P0 | M3 | S-04 |
| D-18 | Sidecar lifecycle and dev spawn | M (2d) | P0 | M3 | D-17 |
| D-19 | Packaging build and smoke test | L (3d) | P0 | M3 | D-17, D-18 |
| D-20 | Electron hardening and upgrade | M (1d) | P1 | M3 | D-19 |
| D-21 | Usage and cost UI | M (1.5d) | P2 | M3 | A-10, A-13 |

---

# Milestone 1: Stable core

## D-01 · Quick wins bundle

**Owner** Dev · **Size** M (1 day) · **Priority** P0 · **Depends on** S-01

**Goal:** remove the crashes and dead wiring found in the code review. One small commit per item.

**Steps**
- [ ] 1. `src/components/AgentChat.tsx`: hooks crash. Move `agentMessages`, `scrollToBottom` and the `useEffect` above the `if (!selectedAgentId || !agent || !project) return ...` block. Inside the effect, start with `if (!agent) return;`.
- [ ] 2. New `src/components/ErrorBoundary.tsx` (class component with `componentDidCatch`, shows the message and a "Reload" button). Wrap `<App />` in `src/main.tsx`.
- [ ] 3. `src/App.tsx`: pass `onOpenConfig={() => setActiveTab("config")}` to `<AgentTree />` (today "Edit Configuration" does nothing).
- [ ] 4. `src/App.tsx`: wrap the body of `bootstrap()` in try/catch. On error call `setBoot("sidecar-down")` and keep the message (`bootError` state) so it shows on screen instead of an endless spinner.
- [ ] 5. `src/api/client.ts`: in `ensurePortInitialized`, on failure set `portInitPromise = null` before rethrowing (today a failed lookup is cached forever). In `request()`, if the error body is JSON with `detail`, throw `new Error(detail)` instead of the raw text.
- [ ] 6. `src/components/ArtifactCard.tsx`: remove the hard-coded `http://127.0.0.1:8000`. Add `src/api/useApiBase.ts` (a hook that awaits `getApiBase()`) and build `fileUrl` from it.
- [ ] 7. `src/components/ArtifactViewer.tsx`: replace `SimpleMarkdown`, `TextBlock` and `renderInlineMarkdown` with `react-markdown` + `remark-gfm` (`npm i react-markdown remark-gfm`). Keep the file-path cards. Style with a wrapper `<div>` (newer react-markdown versions have no `className` prop). Reason: the hand-made renderer turns `web_search_tool` into "web*search*tool".
- [ ] 8. `src/components/AgentEditor.tsx`: the sync `useEffect` resets every field whenever any of nine agent fields change, which wipes unsaved edits after a chat run. Change its deps to `[agent?.id]`. Add a second effect: when `agent.learned_experience` changes and the textarea has not been edited, update only that field. In `handleSaveAll`, send only fields that differ from `agent`.
- [ ] 9. Default model: new `src/config/models.ts` with `DEFAULT_MODELS` per provider (reuse the first entry of each list in `AgentEditor`; for Anthropic use a current id such as `claude-haiku-4-5-20251001` or `claude-sonnet-5-5`, check the provider docs). `useStore.createAgent` passes provider and model. In `AgentChat`, if `agent.model` is empty show "Pick a model in Config" and do not call the API. (A-10 later replaces the list with `/v2/models`.)
- [ ] 10. `python-runtime/app/runtime/engine.py` (legacy, allowed): create the context with `visited_agent_ids=(root_agent_id,)` so the cycle guard fires on the first repeat.
- [ ] 11. `python-runtime/app/tools/web_search.py` (legacy-style tool): delete the fake fallback results. If no backend works, `raise ToolExecutionError("No search backend available. Install 'ddgs' ...")`. Replace `except Exception: pass` with a logged warning.
- [ ] 12. `.gitignore`: add `python-runtime/output/`, `python-runtime/cache/`, `python-runtime/assets/`, `python-runtime/projects/`, `python-runtime/files/`, `python-runtime/production_config.json`. Delete the Tauri section.
- [ ] 13. `README.md`: health-check port is 8000 (not 8756), `USE_MOCK = False`, `character_rig` is no longer a stub, remove "44 of 45", link to `docs/`.

**Done when**
- [ ] Fresh database: creating the first agent does not crash; deleting the last agent does not crash.
- [ ] "Edit Configuration" in the tree menu switches to the Config tab.
- [ ] Stop the backend, start the app: you see an error message, not a spinner.
- [ ] An agent reply containing `web_search_tool` shows the text literally; images and audio artifacts load.
- [ ] Edit a system prompt (do not save), run a chat, come back: your edit is still there.
- [ ] A new agent has a model preselected.
- [ ] `npm run build` passes.

**Watch out:** `react-markdown` is ESM-only; Vite handles it, no config needed.

---

## D-02 · Tests and CI baseline

**Owner** Dev · **Size** M (1 day) · **Priority** P0 · **Depends on** S-01

**Goal:** from now on every PR is checked automatically.

**Steps**
- [ ] 1. `python-runtime/pyproject.toml`: add

```toml
[dependency-groups]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "ruff>=0.5"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = ["live: calls a real LLM (manual only)", "evals: evaluation tasks"]
```

  Run `uv sync --group dev` then `uv run pytest`. The two existing tests must pass (fix imports if not).
- [ ] 2. `tests/conftest.py`: in-memory SQLite engine (`create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})`), a `db_session` fixture, and a `client` fixture (`TestClient(app)` with `app.dependency_overrides[get_db]`).
- [ ] 3. `tests/test_graph.py`: self-link rejected, cycle rejected, valid chain accepted, depth over 8 rejected.
- [ ] 4. `tests/test_memory.py`: cover `plan_compaction` and `assemble_memory_context`. Add one test marked `@pytest.mark.xfail(reason="blind spot, fixed in A-06")` that asserts every older entry is either summarized or included in the output.
- [ ] 5. Frontend: `npm i -D vitest jsdom @testing-library/react @testing-library/jest-dom`. Scripts: `"typecheck": "tsc --noEmit"`, `"test": "vitest"`. In `vite.config.ts` add `test: { environment: "jsdom" }`. Add one smoke test.
- [ ] 6. `.github/workflows/ci.yml` (use current major versions of the actions):

```yaml
name: ci
on: [push, pull_request]
jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: cd python-runtime && uv sync --frozen --group dev
      - run: cd python-runtime && uv run ruff check .
      - run: cd python-runtime && uv run pytest -m "not live"
  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20, cache: npm }
      - run: npm ci
      - run: npm run typecheck
      - run: npm test -- --run
      - run: npm run build
```

- [ ] 7. `.github/pull_request_template.md` with a checklist: task ID, "Done when" ticked, tests added, contract changed?, docs updated?
- [ ] 8. (P2) ESLint with a minimal config.

**Done when**
- [ ] CI is green on `main`.
- [ ] A deliberately failing test turns a PR red (try it once, then revert).
- [ ] `uv run pytest` and `npm test -- --run` pass locally.

**Watch out:** `ruff check` will flag unused imports in several tools (`wave`, `json` in `audio.py`, `asyncio` in `qc.py`). Delete them.

---

## D-03 · Database hardening and migrations

**Owner** Dev · **Size** M (2 days) · **Priority** P0 · **Depends on** S-02

**Goal:** the database enforces its own rules, deleting things cannot leave dangling rows, and schema changes go through Alembic only.

**Files:** `app/db.py`, `app/models.py`, `alembic/env.py`, `alembic.ini`, `app/routers/agents.py`

**Steps**
- [ ] 1. `db.py`: register an `event.listens_for(engine, "connect")` hook that runs `PRAGMA foreign_keys=ON`, `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout=5000`, `PRAGMA synchronous=NORMAL`. (Foreign keys are off by default in SQLite and must be set on every connection.)
- [ ] 2. `models.py`, foreign keys: add `ondelete="CASCADE"` to every FK (`AgentToolLink`, `AgentAgentLink` both sides, `MemoryEntry`, `ExecutionEventRow`, `Tool.project_id`, `Agent.project_id`, `Execution.project_id`). Make `Execution.root_agent_id` `ondelete="SET NULL"` and nullable so history survives agent deletion. Add `passive_deletes=True` on the relationships.
- [ ] 3. `models.py`, the missing relationship: on `Agent` add `parent_links = relationship("AgentAgentLink", foreign_keys="AgentAgentLink.child_agent_id", cascade="all, delete-orphan", passive_deletes=True)` and point `AgentAgentLink.child` at it with `back_populates`. This is what fixes "deleting a sub-agent breaks its parents".
- [ ] 4. Constraints and indexes: `UniqueConstraint("agent_id", "tool_id")` on `AgentToolLink`, `UniqueConstraint("parent_agent_id", "child_agent_id")` on `AgentAgentLink`, index on `execution_events(execution_id, seq)`, index on `memory_entries(agent_id, created_at)`.
- [ ] 5. New columns (all nullable or with defaults, so old rows stay valid):
  - `ExecutionEventRow`: `seq` (int), `span_id`, `parent_span_id`, `kind`, `name`, `status`. Keep the old columns until S-04.
  - `Execution`: `totals` (JSON), `error` (text), `agent_graph_snapshot` (JSON), `ended_at`. Status values: `running | completed | error | cancelled | budget_exceeded | interrupted`.
  - `Agent`: `lessons_enabled` (bool, default false), `params` (JSON, default `{}`). Keep the column `tool_use_schema`; the graph loader maps it to `tool_guidance`.
  - `MemoryEntry`: `kind` (default "fact"), `pinned` (bool), `source_execution_id` (nullable).
  - `Project`: `settings` (JSON, default `{}`).
- [ ] 6. Alembic only: remove `Base.metadata.create_all` and the hand-written `ALTER TABLE` from `init_db()`. Replace with a programmatic `command.upgrade(cfg, "head")`. Build `cfg` from paths relative to the code (`Path(getattr(sys, "_MEIPASS", Path(__file__).parent.parent))` so it also works when packaged), and set `sqlalchemy.url` from `DATABASE_URL` instead of the relative URL in `alembic.ini`.
- [ ] 7. `alembic/env.py`: pass `render_as_batch=True` to `context.configure(...)` (SQLite cannot alter constraints without it).
- [ ] 8. Nobody has real data yet, so: delete `agentforge.db`, then generate **one** baseline migration from the new models (`uv run alembic revision --autogenerate -m "baseline"`), read it, run `uv run alembic upgrade head`. From now on every schema change is a new migration.
- [ ] 9. `routers/agents.py` `list_agents`: use `selectinload(Agent.tool_links), selectinload(Agent.child_links)` (removes the N+1 queries).
- [ ] 10. `tests/test_db_integrity.py`: deleting a child agent removes its link rows; attaching the same tool twice leaves one row; with FKs on, inserting a link to a missing agent raises; deleting a project cascades to agents, tools, executions and events.

**Done when**
- [ ] `alembic upgrade head` works on an empty database and the app boots.
- [ ] All new tests pass.
- [ ] In the app: delete a sub-agent, then chat with its former parent (legacy engine): no "Agent ... not found".

**Watch out:** with FKs on, deletes happen in the database, so the `ondelete` rules must be right before the tests are. If a migration looks empty, check that the models are imported in `alembic/env.py`.

---

## D-04 · Run lifecycle API v2

**Owner** Dev · **Size** M (2 days) · **Priority** P0 · **Depends on** S-02, D-03

**Goal:** `POST /v2/executions` returns immediately; the run happens in the background; events are saved with `seq`, streamed live and can be replayed; runs can be cancelled; stuck runs are cleaned up at startup.

**Files (new):** `app/services/executions.py`, `app/services/graph_loader.py`, `app/routers/executions_v2.py`. Register the router in `main.py`. The old `/executions` routes stay untouched.

**Steps**
- [ ] 1. `graph_loader.py`: `load_agent_graph(db, project_id, root_agent_id) -> AgentGraph` (C-4). Walk children recursively with `selectinload`. For tools use `sanitize_tool_name` and `dedupe_names` from `contracts/naming.py` (names unique inside one agent). Map `tool_use_schema` to `tool_guidance`.
- [ ] 2. `Emitter` (in `executions.py`): holds the `seq` counter and an `asyncio.Lock`. For each `EventDraft`: take the lock, increment `seq`, build the `RunEvent`, save a row with `await asyncio.to_thread(...)` (own short session, so the event loop never blocks), then publish to the hub. The lock keeps ordering correct when tool calls run in parallel.
- [ ] 3. `Hub`: `dict[execution_id, set[asyncio.Queue]]` with `subscribe`, `unsubscribe`, `publish`.
- [ ] 4. `ExecutionManager.start(req)`: insert the `Execution` row (`running`, snapshot of the graph JSON), register `ACTIVE[id] = asyncio.create_task(self._run(...))`, return `{id, status}`.
- [ ] 5. `_run`: open its own `SessionLocal()`, load the graph, emit `execution_started`, call `runner.run(...)` (the runner comes from `get_runner()`, which reads `AGENTFORGE_RUNNER`: `fake` for now), then in `finally` save status, totals, error, `ended_at` and emit `execution_ended`. Catch `asyncio.CancelledError` and record `cancelled` (do not re-raise). Any other exception is recorded as `error` with the message.
- [ ] 6. `cancel(id)`: set the `CancelToken` and call `task.cancel()`.
- [ ] 7. Routes (see C-8): `POST /v2/executions`, `GET /v2/executions` (list), `GET /v2/executions/{id}`, `GET /v2/executions/{id}/events?after_seq=`, `POST /v2/executions/{id}/cancel`, and the WebSocket `/v2/executions/{id}/stream?after_seq=`.
- [ ] 8. WebSocket order matters: **subscribe to the hub first**, then read the backlog from the database after `after_seq`, send it, remember `last_seq`, then drain the queue skipping any `seq <= last_seq`. This guarantees no gaps and no duplicates.
- [ ] 9. `lifespan` in `main.py`: on startup mark every `running` execution `interrupted`. On shutdown cancel active tasks and wait up to 3 seconds.
- [ ] 10. Tests with `TestClient` and the FakeRunner (D-05): the POST returns in under 200 ms for a 3-second scenario; the WebSocket receives events in `seq` order; reconnecting with `after_seq=N` gets only newer events; cancel ends the run with status `cancelled`; a startup cleanup test.

**Done when**
- [ ] `curl -X POST /v2/executions` returns immediately while the run continues.
- [ ] Events stream live, a late subscriber gets the full history, no duplicates.
- [ ] Cancel works and every span in the trace is closed (R1).
- [ ] Killing the backend mid-run and restarting shows that run as `interrupted`.

**Watch out:** the request's DB session is closed when the response is sent, so the background task must open its own. Do not commit inside the emitter while another thread holds the same session.

---

## D-05 · FakeRunner and scenarios

**Owner** Dev · **Size** M (1 day) · **Priority** P0 · **Depends on** S-02, D-04

**Goal:** a scripted Runner that emits correct events, so the API, database and UI can be built and tested with no LLM and no API key.

**Files (new):** `app/dev/fake_runner.py`, `app/dev/scenarios/*.json`, `tests/test_fake_runner.py`, `scripts/export_fixtures.py`

**Steps**
- [ ] 1. Scenario format: a JSON list of ops, for example

```json
[
  {"op": "agent_start", "name": "CEO Agent"},
  {"op": "llm", "ms": 400, "tools": ["research_agent"], "usage": {"in": 1200, "out": 80}, "cost": 0.004},
  {"op": "tool_start", "name": "research_agent", "args": {"task": "Find 3 sources"}},
  {"op": "agent_start", "name": "Research Agent"},
  {"op": "agent_end"},
  {"op": "tool_end", "ok": true, "result": "Found 3 sources"},
  {"op": "agent_end"}
]
```

- [ ] 2. `FakeRunner.run(...)` implements the `Runner` protocol (C-5). It walks the ops, keeps a **stack** of open spans (so `parent_span_id` is right), sleeps `ms` between ops, calls `cancel.raise_if_cancelled()` before every op, and emits events with the `data` keys from the C-2 table. Wrap each span in try/finally so R1 holds on cancel and on error.
- [ ] 3. Ops to support: `agent_start`, `agent_end`, `llm`, `tool_start`, `tool_end`, `sleep`, `approval` (calls `approvals.check`; on deny the next `tool_end` has `ok: false`), `fail` (raises, to test the error path), `budget_exceeded` (returns that `RunResult`).
- [ ] 4. One scenario file each: `single_answer`, `ceo_research` (the table in C-2), `tool_error_recovered`, `long_running` (10 seconds, for Stop), `approval_python`, `budget_exceeded`.
- [ ] 5. Scenario chosen by `req.options.scenario`, default `ceo_research`.
- [ ] 6. `tests/test_fake_runner.py`: run each scenario with a recording `emit` and validate with the contract checker from S-02 (R1 to R3). Cancel `long_running` after 1 second and assert every span ended with `cancelled`.
- [ ] 7. `scripts/export_fixtures.py` writes each scenario's event list to `src/lib/__fixtures__/<scenario>.json`. D-06 tests use them.

**Done when**
- [ ] All six scenarios pass the contract checker.
- [ ] `POST /v2/executions` with `{"options": {"scenario": "long_running"}}` produces a streamable trace you can cancel.

**Watch out:** keep it dumb. No LLM concepts, no prompts. It is a test tool.

---

## D-06 · Run tree UI v2

**Owner** Dev · **Size** L (3 days) · **Priority** P0 · **Depends on** D-04, D-05

**Goal:** a correct live tree of agents, LLM calls and tool calls, with details, status, cost and a Stop button.

**Files (new):** `src/lib/buildSpanTree.ts`, `src/hooks/useRunStream.ts`, `src/components/run/{RunPanel,RunTree,SpanDetails,RunHeader,RunsList}.tsx`. Update `src/App.tsx`, `src/api/client.ts`. The old `ExecutionTree.tsx` and `useExecutionStream.ts` stay until S-04.

**Steps**
- [ ] 1. `client.ts`: add `api.v2` with `startRun`, `getRun`, `getEvents(id, afterSeq)`, `cancelRun`, `listRuns`, `approve`. Types come from `src/contracts.ts`.
- [ ] 2. `buildSpanTree(events)` as a **pure function** returning `{ roots: SpanNode[]; run: { status, totals, error } | null }`. Algorithm: sort by `seq`. `span_started` creates a node `{id, parentId, kind, name, status: "running", startedAt, data}` and attaches it under its parent (or to roots). `span_ended` sets status, `endedAt`, `durationMs` and merges `data`. `execution_ended` fills `run`. Sum tokens and cost from `llm_call` spans up the tree. If a parent is unknown, attach to roots and mark `orphan: true`; never throw.
- [ ] 3. Vitest tests using the fixtures from D-05: expected shape for each scenario; the root agent is `ok` when finished; `long_running` shows `cancelled` spans; `tool_error_recovered` shows an `error` tool_call inside an `ok` agent.
- [ ] 4. `useRunStream(executionId)`: load `GET /v2/executions/{id}` and its events; open the WebSocket with `after_seq=lastSeq`; append events and **dedupe by `seq`**; if the socket closes before `execution_ended`, reconnect after 1 s with back-off up to 10 s; after 3 failures fall back to polling `/events?after_seq=` every 2 s; stop everything after `execution_ended`. Returns `{ events, tree, run, cancel }`.
- [ ] 5. `RunTree`: one row per span with an icon by kind, status dot (running pulses, ok green, error red, cancelled grey), duration, tokens and cost badge, collapse/expand, auto-scroll to the newest running span, and a "Show LLM calls" toggle.
- [ ] 6. `SpanDetails`: for the selected span show args, result preview, error, usage, timing and artifacts, with a Copy button.
- [ ] 7. `RunHeader`: run status, totals (calls, tokens, cost or "n/a", elapsed time) and the Stop button (disabled unless running).
- [ ] 8. `RunsList`: dropdown of recent runs (`listRuns`) to reopen an old trace.
- [ ] 9. If an `approval_requested` event has no matching `approval_resolved`, show a "Waiting for your approval" banner (the real dialog is D-12).
- [ ] 10. `App.tsx`: the right column shows `RunPanel` when `engine === "v2"` (toggle from D-07), otherwise the old tree.

**Done when**
- [ ] Every FakeRunner scenario renders the expected structure; the root agent turns "completed" when the run ends.
- [ ] Stop on `long_running` ends the run within 2 seconds.
- [ ] After reloading the app you can reopen the run from `RunsList`.
- [ ] `buildSpanTree` tests pass.

**Watch out:** do not key anything by display name; use `span_id`. Keep fetching in hooks and `lib/`, not inside presentational components.

---

## D-07 · Chat v2 (history, Stop, usage)

**Owner** Dev · **Size** M (1.5 days) · **Priority** P0 · **Depends on** D-04, D-05

**Goal:** chat uses the new API: a real `history` array (no marker strings), an instant response, Stop, a usage line and proper error styling. The old engine stays reachable through a developer toggle until S-04.

**Files:** `src/components/AgentChat.tsx`, `src/store/useStore.ts`, `src/components/SettingsModal.tsx`, new `src/config/chat.ts`

**Steps**
- [ ] 1. Store: add `engine: "legacy" | "v2"` (saved in localStorage; default `legacy`, switched to `v2` in S-03). Settings gets a "Developer" section with the toggle.
- [ ] 2. v2 send path: `history = messages.slice(-N).map(m => ({ role: m.sender === "user" ? "user" : "assistant", content: m.text }))` with `N = 10` from `config/chat.ts`. Call `api.v2.startRun({ project_id, root_agent_id, task: userText, history })`, keep the returned id as `activeRunId`, and call `onRunExecution(id)` immediately so the tree is live.
- [ ] 3. While running: show "Working..." plus the name of the most recent running span (from `useRunStream`) and a Stop button.
- [ ] 4. On `execution_ended` append the agent message with `final_output` and style by status: `completed` normal; `error` red box with the message; `cancelled` grey "Stopped"; `budget_exceeded` amber "Stopped: budget reached" plus the partial output.
- [ ] 5. Under each agent message add a small usage line, for example `1.2k in · 0.4k out · $0.003 · 4.1 s` (`n/a` when cost is null).
- [ ] 6. The v2 path has no polling loop, no `[RECENT CONVERSATION HISTORY]` markers, and no `updateAgent(agent.id, {})`. (The legacy path keeps them until S-04.)
- [ ] 7. Component test with a mocked `api.v2`: send, working state, final answer; Stop; error styling.

**Done when**
- [ ] With FakeRunner, chat works end to end and shows the usage line.
- [ ] `grep -n "RECENT CONVERSATION" src` only finds the legacy branch.
- [ ] Flipping the toggle to `legacy` still works against a real provider key.

---

## D-08 · Tool v2 base, registry and legacy adapter

**Owner** Dev · **Size** M (2 days) · **Priority** P0 · **Depends on** S-02

**Goal:** one tool interface the Runner can rely on (C-3), with every existing tool usable through an adapter, so AI is never blocked on tool work.

**Files:** `app/tools/adapter.py` (new), `app/tools/specs.py` (new), `app/tools/registry.py`, `app/contracts/naming.py`, `scripts/try_tool.py` (new)

**Steps**
- [ ] 1. Implement `sanitize_tool_name` and `dedupe_names` (`contracts/naming.py`) with tests: spaces, parentheses, unicode, empty string becomes `tool`, a leading digit gets prefix `t_`, 64-character cap, duplicates become `x`, `x_2`, `x_3`.
- [ ] 2. `adapter.py`: `LegacyToolAdapter(Tool)` wraps an old `base.Tool`. Its `Input` is `LegacyInput(input: str)`. `run(args, ctx)` calls `legacy.execute(args.input, context=ctx)`, wraps the returned string in `ToolResult(content=...)` and converts `ToolExecutionError` into `ToolError`. `kind` and `default_description` come from the legacy tool. `permissions` come from a map inside the adapter: `python` is `{"subprocess"}`, `http_request` and `web_search` are `{"net"}`, `file_system` is `{"fs_write"}`, everything else is empty (D-09 reviews each tool).
- [ ] 3. `registry.py`: add `DefaultToolFactory.build(binding) -> Tool`. It calls the existing `build_tool(binding.kind, binding.config)` and wraps the result in the adapter. Add `NATIVE_TOOLS: dict[str, type[Tool]]`; entries there (written by AI in A-05) take precedence over adapters.
- [ ] 4. `specs.py`: `tool_spec(binding, tool) -> ToolSpec` with `name = binding.name`, `description = binding.description or tool.default_description`, `parameters = tool.Input.model_json_schema()`. The Runner uses this one helper, so naming and schemas are identical everywhere.
- [ ] 5. `scripts/try_tool.py <kind> '<json args>'`: builds the tool through `DefaultToolFactory`, runs it with a temporary workspace and prints the `ToolResult`. This lets AI try any tool without the UI.
- [ ] 6. Tests: the adapter converts `ToolExecutionError` to `ToolError`; two bindings of the same kind with different names coexist; the adapter's JSON Schema is `{"input": string}`; a native tool beats the adapter.
- [ ] 7. Do **not** change `build_tool` behavior: the legacy engine still depends on it.

**Done when**
- [ ] `uv run python scripts/try_tool.py http_request '{"input": "GET https://example.com"}'` prints a result.
- [ ] Tests pass.

---

# Milestone 2: Safe and solid

## D-09 · Workspace path resolver, tool migration, video-pack switch

**Owner** Dev · **Size** L (2.5 days) · **Priority** P0 · **Depends on** D-08

**Goal:** no tool can read or write outside its run workspace, and the 45 video tools are parked behind a switch.

**Files:** new `app/infra/workspace.py`; edit `app/tools/{audio,character,composition,graphics,qc,rendering,scene,asset_cache,filesystem,catalog}.py`, `app/routers/catalog.py`, `src/components/{ArtifactCard,ArtifactViewer,ToolCatalogModal}.tsx`

**Steps**
- [ ] 1. Implement `RunWorkspace` (C-3) in `infra/workspace.py`. `root = <data_dir>/runs/<execution_id>/` (until D-17: `python-runtime/.data/runs/...`). `resolve(rel)` rejects empty strings, absolute paths, drive letters and any `..` segment, then checks `(root / rel).resolve().is_relative_to(root.resolve())` (this also blocks symlink escapes). `new_path(name)` sanitizes the name, makes it unique (`name`, `name_2`...) and creates parent folders. Add `safe_id(value)` that only accepts `^[A-Za-z0-9_-]{1,64}$`. All failures raise `ToolError`.
- [ ] 2. Add a second, read-only root for reusable project files (voices, characters, fonts, templates): `workspace.asset(rel)` resolves under `<data_dir>/assets` with the same rules.
- [ ] 3. Tool helpers: `out_path(ctx, params, key, default_name)` for outputs and `in_path(ctx, params, key)` for inputs. Both go through the workspace. Tools return **relative** paths in their JSON so the model passes them on unchanged.
- [ ] 4. Migrate every tool that takes a path or id (replace raw `Path(params[...])`):
  - `audio.py`: voice_generator (`output_path`), audio_processing (`audio_path`, `output_path`), audio_alignment (`audio_path`), audio_mixer (`voice_path`, `music_path`, `output_path`)
  - `character.py`: character_rig (`output_image_path`, `output_video_path`, `audio_path`), character_asset_manager (`character_id` via `safe_id`, assets root)
  - `composition.py`: composition_engine (`layers[].image_path`, `output_path`), effects_engine (`input_path`, `output_path`)
  - `graphics.py`: visual_asset_manager (`name`, assets root), evidence_graphics, data_visualization, headline_card, debate_graphics, caption_engine, typography_engine (`output_path`)
  - `qc.py`: audio_qc (`audio_path`), video_qc (`video_path`), automated_preview_qc (`preview_path`)
  - `rendering.py`: preview_renderer, final_renderer, render_worker (`image_path`, `audio_path`, `output_path`, `job_id` via `safe_id`), render_queue (queue file under `<data_dir>/queues/`)
  - `scene.py`: scene_template_manager (`template_id` via `safe_id`, templates under assets)
  - `asset_cache.py`: project_manager (`episode_id` via `safe_id`), asset_cache_store (`src_path` must be in the workspace, `category` and `name` via `safe_id`), production_config (fixed path under the data dir)
  - `filesystem.py`: root becomes `<workspace>/files`
- [ ] 5. Legacy fallback: the old engine passes no workspace. Add `workspace_from(context)` that returns `context.workspace` if present, else a default `./output` workspace (3 lines). Remove it in S-04.
- [ ] 6. File serving: new route `GET /v2/executions/{id}/files/{relpath:path}` (C-8) that returns `FileResponse` after `workspace.resolve`. `ArtifactCard` builds URLs from the execution id, the relative path and the API base (plus `?token=` once D-10 lands).
- [ ] 7. Video pack switch: add `pack: str` to `CatalogEntry` (`"video"` for all 45). `/catalog/shelves?pack=video` filters. Settings gets "Enable video pack" (default off, saved in localStorage). `ToolCatalogModal` shows no video shelves unless it is on. Fix catalog text that is wrong today: `character_rig` is no longer a stub, `audio_mixer` has no ducking yet, `caption_engine` is SRT only.
- [ ] 8. Tests, parametrized over every path-taking tool: `../../x`, `/etc/x`, `C:\x`, and a symlink inside the workspace pointing outside must all raise `ToolError` and write nothing outside the root.

**Done when**
- [ ] The tests above pass for every tool in step 4.
- [ ] `grep -rn "Path(params" python-runtime/app/tools` finds nothing outside the helpers.
- [ ] An image produced by a tool shows up in chat through the new file route.
- [ ] With the video pack off, the catalog modal shows no video shelves.

**Watch out:** ffmpeg and PIL get absolute paths *after* resolution, which is fine. Never accept an absolute path from the model.

---

## D-10 · API auth and CORS

**Owner** Dev · **Size** M (1.5 days) · **Priority** P0 · **Depends on** D-04

**Goal:** only the app can call the local API, not other programs or web pages.

**Files:** `electron/main.js`, `electron/preload.cjs`, `src/electron.d.ts`, `src/api/client.ts`, `python-runtime/main.py`, new `app/infra/auth.py`

**Steps**
- [ ] 1. `main.js`: at startup `const token = crypto.randomBytes(32).toString("hex")`. Pass it to the sidecar as env `AGENTFORGE_TOKEN`. Add `ipcMain.handle("get-api-token", () => token)`, expose `getApiToken` in `preload.cjs` and `electron.d.ts`.
- [ ] 2. `infra/auth.py`: `require_token(request)` reads `Authorization: Bearer ...` and compares with `secrets.compare_digest`. The `?token=` query parameter is accepted **only** on the WebSocket and the file route. If `AGENTFORGE_TOKEN` is not set, refuse to start unless `AGENTFORGE_DEV=1` (then the token is `dev`).
- [ ] 3. `main.py`: add `dependencies=[Depends(require_token)]` to every router; `/health` stays open. For the WebSocket, check `token` before `accept()` and reject otherwise. Replace the unauthenticated `StaticFiles` mount at `/files` with a token-protected route (legacy artifacts only, removed in S-04).
- [ ] 4. CORS: replace `allow_origins=["*"]` with `["http://localhost:5173", "null"]` (`null` is the Origin of `file://` pages in the packaged app) and `allow_headers=["Authorization", "Content-Type"]`.
- [ ] 5. `client.ts`: fetch the token once via `window.electronAPI.getApiToken()` (browser-only dev: `import.meta.env.VITE_DEV_TOKEN`) and add the header to every request. WebSocket URLs get `&token=`.
- [ ] 6. README dev flow: `AGENTFORGE_DEV=1 uv run python main.py` plus `VITE_DEV_TOKEN=dev` in `.env.local`.
- [ ] 7. Tests: no token gives 401, wrong token 401, correct token 200, WebSocket without token is rejected, `/health` is open, and a CORS preflight from `https://example.com` returns no allow-origin header.

**Done when**
- [ ] From the DevTools console of any other website, `fetch("http://127.0.0.1:8000/v2/executions")` fails.
- [ ] The app works normally and all tests pass.

**Watch out:** `<img>` and `<audio>` cannot send headers, which is why the file route accepts `?token=`. Never log URLs that contain the token.

---

## D-11 · API keys flow

**Owner** Dev · **Size** M (1 day) · **Priority** P1 · **Depends on** D-10

**Goal:** the UI never receives a stored key back; Electron's main process hands keys to the sidecar directly.

**Files:** `electron/main.js`, `electron/preload.cjs`, `src/electron.d.ts`, `src/api/keychain.ts`, `src/api/client.ts`, `src/components/SettingsModal.tsx`, `app/routers/settings.py` (moves under `/v2/settings`)

**Steps**
- [ ] 1. Remove `get-api-key` from IPC and `preload.cjs`. Add `has-api-key(provider)` returning `{ present, last4 }`. Keep `save-api-key` and `delete-api-key`.
- [ ] 2. `saveApiKey` returns `{ ok: false, reason: "encryption-unavailable" }` when `safeStorage.isEncryptionAvailable()` is false, unless `AGENTFORGE_ALLOW_PLAINTEXT_KEYS=1` is set (Linux without a keyring). No more silent base64.
- [ ] 3. Once the sidecar is ready (and after every save or delete), the main process posts the decrypted keys to `POST /v2/settings/keys` with the bearer token, using Node's built-in `fetch`.
- [ ] 4. `SettingsModal`: show "Saved (...abcd)" with Replace and Remove buttons instead of pre-filled password inputs. Show the encryption-unavailable message when returned.
- [ ] 5. Delete `getKeys` and `syncKeysToBackend`. Browser-only dev: keys typed in Settings go straight to `POST /v2/settings/keys` and are never stored in localStorage.
- [ ] 6. `settings.py`: keep the environment-variable approach and never log key material, only presence.

**Done when**
- [ ] `window.electronAPI.getApiKey` is `undefined` in DevTools.
- [ ] Keys still work after a restart.
- [ ] With encryption unavailable the UI shows a clear message.

---

## D-12 · Approvals and project settings

**Owner** Dev · **Size** M (2 days) · **Priority** P0 · **Depends on** D-08, S-03

**Goal:** dangerous tool calls pause for the user's decision, and project-level settings (parallel tools, budget, tool policy) finally have a UI.

**Files:** new `app/infra/approvals.py`, `app/routers/executions_v2.py`, new `src/components/run/ApprovalDialog.tsx`, new `src/components/ProjectSettings.tsx`

**Steps**
- [ ] 1. `ApprovalGate` implements the protocol in C-5. `check(...)` looks up the policy for the tool kind in `project.settings["tool_policy"]` (`allow` / `ask` / `deny`). Defaults: `python` ask, `http_request` ask, `web_search` allow, `file_system` allow (workspace only), everything else allow. `deny` returns `False` at once. `ask` (or `force=True`) creates an `approval_id`, emits `approval_requested`, waits on an `asyncio.Future` stored in `PENDING[approval_id]` (timeout from Q6, default 5 minutes), then emits `approval_resolved`. A timeout counts as deny. "allow_run" remembers `(execution_id, tool)`.
- [ ] 2. If the run is cancelled while waiting, resolve the future with deny and clean up.
- [ ] 3. Route `POST /v2/executions/{id}/approvals/{approval_id}` with `{decision}` sets the future's result. 404 if unknown or expired.
- [ ] 4. `ApprovalDialog`: opens for any `approval_requested` event without a matching `approval_resolved`. Shows tool name, permissions, pretty-printed args and the reason. Buttons: Allow once, Allow for this run, Deny. It replaces the banner from D-06.
- [ ] 5. `ProjectSettings` (TopBar project menu): parallel tools toggle (this finally wires up `updateProjectSettings`), budget fields (max cost USD, max LLM calls, max seconds) and a tool policy table (Ask / Allow / Deny per tool kind), saved in `Project.settings`. New run requests use these as defaults for `RunOptions`.
- [ ] 6. Tests with the FakeRunner `approval_python` scenario: approve continues the run, deny ends that tool call with an error saying it was denied, timeout counts as deny.

**Done when**
- [ ] A `python` call pauses until you decide.
- [ ] Deny returns a tool error to the model and the run continues.
- [ ] Cancelling while the dialog is open ends cleanly.
- [ ] The project settings panel changes the next run's behavior.

**Watch out:** the gate waits only on futures. Never block the event loop.

---

## D-13 · Python and HTTP tool safety

**Owner** Dev · **Size** M (1.5 days) · **Priority** P0 · **Depends on** D-09

**Files:** `app/tools/python_exec.py`, `app/tools/http_request.py`, new `app/infra/ssrf.py`

**Steps**
- [ ] 1. Python tool: strip Markdown fences (` ```python ... ``` `) from the input; cap stdout and stderr at 10,000 characters each (append `…[truncated]`).
- [ ] 2. Windows: build the subprocess env with `SYSTEMROOT`, `TEMP`, `TMP` and a minimal `PATH` (Python will not start without `SYSTEMROOT`), skip `preexec_fn`, use `creationflags=subprocess.CREATE_NO_WINDOW`. macOS: wrap each `resource.setrlimit` call in try/except (`RLIMIT_AS` is unreliable there), keep `RLIMIT_CPU`.
- [ ] 3. Frozen builds: if `getattr(sys, "frozen", False)`, run `[sys.executable, "--run-snippet", script_path]` (the flag is implemented in D-19). Fix the docstring: say what is limited (CPU, memory, wall clock, environment) and what is **not** (file reads, network). Permission `{"subprocess"}`, default policy `ask` (D-12).
- [ ] 4. `infra/ssrf.py`: `assert_public_url(url)`. Allow only `http`/`https`. Resolve the host with `socket.getaddrinfo` and reject any address that is loopback, private, link-local, multicast, reserved or unspecified (`ipaddress` module), and the app's own port.
- [ ] 5. `http_request.py`: `follow_redirects=False`; follow up to 5 redirects manually and run `assert_public_url` on every hop. Use `client.stream` and stop reading at 1 MB (return `truncated: true`). A-11's `web_fetch` reuses this helper.
- [ ] 6. Tests: refused: `http://127.0.0.1:8000/health`, `http://localhost`, `http://169.254.169.254/`, `http://10.0.0.1/`, `http://[::1]/`, and a redirect from a local test server to `127.0.0.1`. Allowed: a public URL (mock transport). Python: fences stripped, output capped, timeout works, the environment contains no API keys.

**Done when:** all tests pass and `http_request` to the app's own API is refused.

**Watch out:** DNS rebinding between the check and the connect is a known gap; note it in the docstring.

---

## D-14 · Conversations and run history

**Owner** Dev · **Size** M (1.5 days) · **Priority** P1 · **Depends on** D-07

**Steps**
- [ ] 1. Migration: `conversations(id, project_id, agent_id, title, created_at)`, `messages(id, conversation_id, role, content, execution_id, created_at)`, `message_feedback(message_id, value, note, created_at)` where `value` is -1 or 1.
- [ ] 2. Routes: list/create/delete conversations, list/append messages, `PUT /v2/messages/{id}/feedback`.
- [ ] 3. Store: replace the in-memory `chatMessages` with loading from the API when an agent is selected. Add a "New chat" button. Title = first user message.
- [ ] 4. `AgentChat`: persist each user and agent message (agent messages carry `execution_id`). Clicking an agent message opens its trace in the right panel. Add thumbs up/down under agent messages (optional note on thumbs down). `history` for new runs = the current conversation.

**Done when:** restart the app and the chat is still there; a past answer opens its trace; feedback persists (A-07 reads it).

---

## D-15 · Dependencies and system check

**Owner** Dev · **Size** M (1 day) · **Priority** P1 · **Depends on** D-09

**Steps**
- [ ] 1. `pyproject.toml` groups: `video = ["matplotlib", "piper-tts"]`, `search = ["ddgs", "beautifulsoup4"]` (A-11 may change it), `build = ["pyinstaller"]`.
- [ ] 2. `tools/shared.py`: `require_binary(name, hint)` using `shutil.which` (and the `vendor/` folder from D-19) that raises `ToolError(f"{name} not found. {hint}")`. Use it everywhere a tool calls `ffmpeg`, `ffprobe` or `piper`.
- [ ] 3. Replace the blocking `subprocess.run` calls in `audio._ffprobe_duration` and `qc._ffprobe_json` with `asyncio.create_subprocess_exec` (they freeze the event loop today).
- [ ] 4. `GET /v2/system/check` returns `[{name, ok, detail, fix}]` for: ffmpeg, ffprobe, piper, Python packages (matplotlib, ddgs), keys present per provider, data dir writable, database reachable, free disk over 1 GB. Settings gets a "System check" tab.

**Done when:** on a machine without ffmpeg the tab is red with an instruction, and a video tool returns a tool error instead of crashing the run.

---

## D-16 · Memory and lessons UI

**Owner** Dev · **Size** M (1.5 days) · **Priority** P1 · **Depends on** A-06, A-07

**Steps**
- [ ] 1. Implement `SqlMemoryStore` and `SqlLessonStore` (`app/services/memory_store.py`) for AI's final protocols. Add the `lessons` table (and `lesson_versions` if AI asks) by migration.
- [ ] 2. Routes: `GET/DELETE /v2/agents/{id}/memory`, `PATCH .../memory/{mid}` (pin), `GET /v2/agents/{id}/lessons`, `PATCH`/`DELETE .../lessons/{lid}` (archive, restore, edit).
- [ ] 3. Agent Config tab: a **Memory** section (toggle, list with kind/date/pinned, delete, pin, clear all) and a **Lessons** section (toggle, list with status, archive/restore/delete, history if versioned).
- [ ] 4. The old "Learned Experience" textarea becomes a read-only "Legacy notes (not used)" box, hidden when empty. Stop sending `learned_experience` from the editor.

**Done when:** toggles and edits work, and a deleted memory is absent from the next run's prompt.

---

# Milestone 3: Installable app

## D-17 · Paths and data directory

**Owner** Dev · **Size** M (1 day) · **Priority** P0 · **Depends on** S-04

**Steps**
- [ ] 1. `app/infra/paths.py`: `data_dir()` = env `AGENTFORGE_DATA_DIR`, else `python-runtime/.data` in dev. Subfolders: `db/`, `runs/`, `assets/`, `queues/`, `logs/`. Add `.data/` to `.gitignore`.
- [ ] 2. Use it in `db.py` (`DATABASE_URL`), `main.py` (remove `OUTPUT_DIR`), `alembic/env.py`, the workspace root and every tool default root.
- [ ] 3. `electron/main.js` passes `AGENTFORGE_DATA_DIR = app.getPath("userData") + "/data"` to the sidecar.

**Done when:** `grep -rn '"\./\(output\|assets\|cache\|files\|projects\)' python-runtime/app` finds nothing, and changing the env var moves the database and all runs.

---

## D-18 · Sidecar lifecycle and dev spawn

**Owner** Dev · **Size** M (2 days) · **Priority** P0 · **Depends on** D-17

**Steps**
- [ ] 1. `main.py`: pre-bind a socket (`sock.bind(("127.0.0.1", 0))`), run `uvicorn.Server(config).serve(sockets=[sock])`, and print `AGENTFORGE_READY:<port>` only after `server.started` is true.
- [ ] 2. Parent watchdog: when `AGENTFORGE_WATCH_PARENT=1`, a thread blocks on `sys.stdin.buffer.read()` and exits the process on EOF (Electron closing the pipe). Electron sets that variable.
- [ ] 3. `main.js`: `spawn(..., { windowsHide: true })`; `app.requestSingleInstanceLock()` (focus the existing window on `second-instance`); on quit send SIGTERM, then `taskkill /pid <pid> /T /F` on Windows after 2 s.
- [ ] 4. Dev spawn: use `uv run python main.py` with `cwd = python-runtime` instead of bare `python3`.
- [ ] 5. Remove the hard-coded `8000` from `client.ts` and `ArtifactCard.tsx`; the port comes only from IPC (browser-only dev: `VITE_API_BASE`).

**Done when:** killing Electron from Task Manager leaves no Python process within 2 seconds; starting the app twice focuses the first window; `npm run dev` starts the backend by itself.

---

## D-19 · Packaging build and smoke test

**Owner** Dev · **Size** L (3 days) · **Priority** P0 · **Depends on** D-17, D-18

**Steps**
- [ ] 0. **Early spike (end of M1, half a day):** run `npm run dist` once, unchanged, only to write down what breaks. Do not fix anything yet.
- [ ] 1. `python-runtime.spec`: remove the `engineio` hidden import, set `upx=False`, use `collect_all("litellm")` if LiteLLM stays (A-01 D-2), keep alembic files in `datas`.
- [ ] 2. `main.py`: handle `--run-snippet <path>` first thing (`runpy.run_path(path, run_name="__main__")` then exit) so the python tool works in the frozen build.
- [ ] 3. Optional: bundle a static ffmpeg for your OS in `python-runtime/vendor/ffmpeg/` (gitignored, shipped via `extraResources`); `require_binary` checks it first.
- [ ] 4. Icon: export `app-icon.svg` to a 1024x1024 `build/icon.png` (electron-builder converts it per platform).
- [ ] 5. `scripts/build.ps1` / `scripts/build.sh`: `uv sync --frozen --group build`, `uv run pyinstaller python-runtime.spec`, `npm ci`, `npm run dist`.
- [ ] 6. Write `docs/SMOKE.md`: on a clean user account or VM: install, start, create agent, set key, run a chat, approve a `python` call, quit, confirm no leftover process, relaunch and confirm data persisted in the user-data folder.

**Done when:** an installer builds on your OS and passes `docs/SMOKE.md`. (Unsigned builds show an OS warning; that is fine for personal use.)

---

## D-20 · Electron hardening and upgrade

**Owner** Dev · **Size** M (1 day) · **Priority** P1 · **Depends on** D-19

**Steps**
- [ ] 1. Upgrade `electron` and `electron-builder` to supported majors (Electron 31 is far out of support); re-run the smoke test.
- [ ] 2. `webPreferences.sandbox: true`; `setWindowOpenHandler` denies everything except https links opened with `shell.openExternal`; block `will-navigate` away from the app.
- [ ] 3. Production-only CSP (a Vite `transformIndexHtml` plugin): `default-src 'self'; connect-src 'self' http://127.0.0.1:* ws://127.0.0.1:*; img-src 'self' data: http://127.0.0.1:*; media-src 'self' http://127.0.0.1:*; style-src 'self' 'unsafe-inline'; font-src 'self' data:`.
- [ ] 4. Replace Google Fonts with `@fontsource/inter` and `@fontsource/jetbrains-mono`.

**Done when:** DevTools → Network shows no external requests at startup.

---

## D-21 · Usage and cost UI

**Owner** Dev · **Size** M (1.5 days) · **Priority** P2 · **Depends on** A-10, A-13

**Steps**
- [ ] 1. `GET /v2/usage?project_id=&days=` aggregates `executions.totals` by day, model and agent.
- [ ] 2. A "Usage" tab with simple bars, totals, "n/a" for unknown prices, and a warning when a run nears its budget.

**Done when:** project cost for the last 7 days matches the sum of its runs.

---

## After M3 (Dev side, outline only)

Import/export of projects (YAML/JSON), a graph canvas (React Flow) for agent hierarchies, an artifact browser, run comparison, an accessibility pass, a second OS in CI, and (only if you go public) code signing and auto-update. Detailed cards get written at the M3 gate.
