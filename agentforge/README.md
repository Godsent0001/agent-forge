# AgentForge

A desktop AI Agent Builder and Execution Environment: visually compose
recursive AI agent hierarchies where independent tools are reusable
across agents, and agents can themselves become tools for other agents.

This build covers Phases 0 through 9 of the plan. Read this file before
running anything — it tells you exactly what was tested in the sandbox
this was built in (which has no network access) versus what you need to
verify locally.

---

## What's here, by phase

| Phase | What it is | Status |
|---|---|---|
| 0 | Tauri + React + FastAPI scaffold, sidecar wiring | Built. Needs local `npm run tauri dev` to verify. |
| 0.5 | Headless recursive-execution spike (`python-runtime/spike/headless_spike.py`) | **Run and passing** — see below. |
| 1 | Full data model + cycle/depth validation (`app/models.py`, `app/graph.py`) | Schema built; cycle-detection **algorithm unit-tested and passing** (6/6 cases). Full DB/API needs `uv sync` locally (no network here to install SQLAlchemy). |
| 2 | Tool Library: web search, sandboxed Python, filesystem, HTTP (`app/tools/`) | **Sandboxed Python and filesystem tools run and tested locally** (timeout, error propagation, path-escape guard all confirmed). Web search / HTTP use mock backends pending real API keys. |
| 3 | Design system + Agent Tree/Editor/Tool Library UI (`src/components/`) | Built. Needs `npm install` + `npm run tauri dev` to verify visually. |
| 4 | LLM interface, LiteLLM-ready (`app/llm.py`) | Built with a mock fallback (`USE_MOCK = True`) since this sandbox has no network to call a real provider. |
| 5/6 | Production agent loop + recursive execution engine (`app/runtime/`) | Built on the validated Phase 0.5 logic, wired to real DB config/tools/LLM interface. Needs local deps to run end-to-end. |
| 7 | WebSocket live execution events (`app/ws.py`, `src/hooks/useExecutionStream.ts`) | Built. Needs local run to verify the live tree UI. |
| 8 | Design polish: fonts, scrollbars, focus states, motion | Built into `src/index.css` and `tailwind.config.js`. |
| 9 | Packaging: standalone Python sidecar, OS-keychain API key storage | Built (`src-tauri/src/keychain.rs` + `src/components/SettingsModal.tsx`). Needs local Rust build to verify. |

**Why the split:** this sandbox has no network access, so anything requiring
`npm install`, `cargo build`, `uv sync`, or a real LLM/API call could not be
executed here. Everything that *could* run with pure Python and no
dependencies was actually run and its output is shown below — I didn't
just write code and assume it works.

---

## What was actually run and verified in this environment

**Phase 0.5 headless spike** — proved recursion, the 4-layer prompt merge,
and both guards work, before any UI or schema was built on top of them:

```
[ExecutionStarted]
[AgentStarted] CEO Agent task="Analyze the AI video market..."
[ChildAgentStarted] Research Agent
  [AgentStarted] Research Agent task="Research the top 10 AI video companies..."
  [ToolCallStarted] web_search query="top AI video companies pricing enterprise Africa"
  [ToolCallCompleted] web_search
  [AgentCompleted] Research Agent result="..."
[ChildAgentCompleted] Research Agent
[AgentCompleted] CEO Agent result="Based on research: recommend entering..."
[ExecutionCompleted]

Cycle guard demo: OK — CycleDetectedError raised correctly
Depth guard demo: OK — RecursionLimitError raised correctly
```

**Cycle/depth detection algorithm** (`app/graph.py`'s logic, tested standalone):
all 6 cases passed — direct self-cycle, indirect cycle, valid new edge,
depth computation, and rejecting a link that would exceed max depth.

**Sandboxed Python tool** (`app/tools/python_exec.py`): basic execution,
10-second wall-clock timeout enforcement, and error propagation all
confirmed working via subprocess isolation.

**Filesystem tool** (`app/tools/filesystem.py`): read/write/list confirmed
working, and the path-escape guard correctly rejected a `../../etc/passwd`
traversal attempt.

Run any of these yourself:
```bash
cd python-runtime
python3 spike/headless_spike.py
```

---

## Setup (run these yourself — no network in the environment this was built in)

### Prerequisites
- Node.js 18+, npm
- Rust + Cargo (`rustup`)
- Tauri CLI: `cargo install tauri-cli --version "^2.0.0"`
- [`uv`](https://docs.astral.sh/uv/)

### 1. Frontend
```bash
npm install
```

### 2. Python runtime
```bash
cd python-runtime
uv python install 3.11
uv venv --python 3.11
uv sync
uv run python main.py     # sanity check: http://127.0.0.1:8756/health
```

Initialize the DB schema:
```bash
uv run alembic revision --autogenerate -m "initial schema"
uv run alembic upgrade head
```

### 3. Enable a real LLM
Edit `python-runtime/app/llm.py`, set `USE_MOCK = False`. Add `litellm` to
`pyproject.toml` if not already resolved, `uv sync` again. Set API keys via
the in-app Settings (⚙ icon) — they're stored in your OS keychain via the
Rust `keyring` crate, not in a file.

### 4. Sidecar wiring for `npm run tauri dev`
Tauri needs the sidecar binary named with your target triple, e.g.:
```
src-tauri/binaries/python-runtime-x86_64-apple-darwin
src-tauri/binaries/python-runtime-x86_64-pc-windows-msvc.exe
src-tauri/binaries/python-runtime-x86_64-unknown-linux-gnu
```
Get your triple: `rustc -vV | grep host`. Point it at your `uv`-managed
venv's Python + `main.py` for dev; for distribution, bundle a full
`python-build-standalone` interpreter folder instead of relying on
PyInstaller (see the packaging rationale below).

### 5. Run everything
```bash
npm run tauri dev
```
You should get: Vite on :1420 → Tauri window → Python sidecar spawns →
UI bootstraps a default project → Agent Tree/Editor/Execution panels render.

---

## Architecture notes worth knowing before you extend this

- **Tool interface is universal.** `Tool.execute()` is the only method
  both real tools (`app/tools/*.py`) and `AgentTool` (`app/runtime/agent_tool.py`,
  which wraps a child agent) implement. The engine never special-cases
  either — this is the core recursive design from the spec.
- **Cycle/depth guards exist at two layers, deliberately.** `app/graph.py`
  rejects a cyclic/too-deep link *when you try to save it* (better UX).
  `app/runtime/context.py`'s `ExecutionContext.descend()` re-checks *at
  execution time* (defense in depth — never trust only the edit-time check).
- **Python sandboxing is a restricted subprocess**, not a full container.
  Good enough for your own agents' code; not sufficient if you ever accept
  tool code from untrusted third parties. See the comment block at the top
  of `app/tools/python_exec.py`.
- **API keys live in the OS keychain**, not a custom-encrypted file — see
  `src-tauri/src/keychain.rs`. This was a deliberate swap from the original
  plan during the build-plan review.
- **Standalone Python over PyInstaller for packaging.** Avoids the
  hidden-import guessing, antivirus false positives, and slow unpacking
  that PyInstaller sidecars are prone to. Use `python-build-standalone` +
  `uv` instead, bundled as a Tauri external binary resource.

## What's explicitly not built yet
- Real search/HTTP backends (currently mocked — swap the `search_fn` /
  `request_fn` in `app/tools/web_search.py` / `http_request.py`)
- Multi-project switcher UI (single default project for now)
- Parallel/concurrent child-agent execution (the engine runs sequentially;
  `asyncio.gather` over independent branches is a natural next step)
- Auto-update wiring, OpenTelemetry tracing, Monaco editor for prompts
  (currently plain textareas)
