# Tasks for Dev (platform, UI, safety, packaging)

You own everything that is not the agent "brain": Electron, React UI, FastAPI routes, database, tool infrastructure and safety, tests/CI and packaging. Read `PLAN.md` first (rules, ownership, milestones), then `CONTRACTS.md` (the interfaces you build against).

> **Precedence (added 2026-10-06).** Where `PLAN.md` section 6b (memory), 6c (large inputs) or 2b (Ollama) differs from a card below, **PLAN.md wins**. Changed cards: **D-08** (+ pagination convention, workspace write call; 2.5d), **D-09** (+ paginated read, grep and stat file tools; 3d), **D-15** (+ FTS5 and Ollama system checks), **D-16** (replaced by D-16a to D-16e, in M2b). All other cards are unchanged. The contracts are drafted in `contracts-v1`; start from `docs/CONTRACTS.md`.

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
