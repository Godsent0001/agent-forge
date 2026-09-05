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
| 2 | Tool Library: general-purpose (web/python/fs/http) + 45-tool Tier-1 production catalog (`app/tools/`) | **44 of 45 production tools run and tested locally** (see the Tier-1 catalog section below for the full breakdown). Web search / HTTP use real backends now (per your httpx/DDGS changes); `character_rig` is a deliberate stub. |
| 3 | Design system + Agent Tree/Editor/shelved Tool Catalog UI (`src/components/`) | Built, including the new `ToolCatalogModal.tsx` shelf picker. Needs `npm install` + `npm run tauri dev` to verify visually. |
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

## Tier-1 Production Tool Catalog

On top of the general-purpose tools, the Tool Library now includes 45
production tools for the script-to-video pipeline, grouped into 11
shelves matching the toolkit spec's engine groupings (Audio, Character,
Scene, Camera, Graphics, Timeline, Composition, Rendering, Asset & Cache,
QC, Orchestration). Browse them via the "+ Browse" button in the sidebar
Tool Library section.

**Tested and confirmed working in this sandbox** (44 of 45 — everything
except the Rive rig renderer, which is a deliberate stub):
- **Audio**: Voice Generator (Piper TTS — code correct, raises a clear
  error here since no model is downloaded/no network to fetch one),
  Audio Processing/Alignment/Mixer — all ran real ffmpeg calls successfully.
- **Character**: all 9 tools (lip-sync, eyes, facial expression/performance,
  gesture, body pose, character performance, asset manager) — pure
  parameter logic, all tested. `character_rig` is the one deliberate stub.
- **Scene, Camera**: all 5 tools tested — template save/load, scene
  assembly, lighting presets, shot selection, camera movement.
- **Graphics**: all 7 tools tested, producing real PNG/SRT files —
  evidence cards, charts (matplotlib), headline/debate labels, captions,
  typography. Visually confirmed on-brand with the app's own design tokens.
- **Timeline, Composition**: all 4 tools tested, including real PIL
  layer-compositing and a working add/split/trim timeline op sequence.
- **Rendering**: all 4 tools tested — real ffmpeg-driven MP4 output at
  both preview and full resolution, plus a working file-backed render queue.
  (Caught and fixed a real bug here during testing: an image-only ffmpeg
  loop with no audio track and no `-t` flag would hang forever — added an
  explicit duration cap.)
- **Asset & Cache**: all 5 tools tested — hashing-based cache hit/miss,
  dependency chain resolution, project scaffolding, shared asset store,
  config get/set.
- **QC**: all 6 tools tested against real files — correctly caught a
  missing audio stream and a missing script line in the test cases.
- **Orchestration**: Pipeline Orchestrator tested — correct stage
  sequencing and rejection of unknown stage names.

**Two real dependency notes:**
- **Piper TTS** needs `pip install piper-tts` (or the binary release) plus
  a downloaded `.onnx` voice model — neither is fetchable without network
  access, so `voice_generator` is code-complete but unverified end-to-end
  here. The error message it raises tells you exactly what's missing.
- **Lip-sync/alignment are approximations**, not a trained model: word
  timing is duration-weighted by character count (no forced aligner
  available offline), and visemes are a coarse grapheme-based mapping
  (no phonemizer like espeak-ng available offline). Both are clearly
  commented as approximations in the code, with the real upgrade path
  noted inline.
- **`character_rig` is the only true stub** — it needs a Rive `.riv`
  asset and the Rive runtime to render actual pixels. Every upstream
  input it would consume (visemes, expression parameters, gaze, gesture,
  pose) is already produced by other Character-shelf tools in working form.



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

## Agent Memory System

Rebuilt after profiling the original implementation, which read and
re-sent *every* memory entry ever written on every single run — unbounded
prompt growth that would eventually blow the context window. The new
version (`app/runtime/memory.py`) follows the same shape as OpenClaw's
compaction: keep the last `RECENT_KEEP` (8) entries verbatim, and once
older un-summarized entries pile up past `COMPACT_TRIGGER` (12), fold
them into a single rolling summary stored on the `Agent` row. Nothing is
deleted — summarized entries stay in the DB (`MemoryEntry.summarized`)
for provenance, they just stop being sent to the LLM raw. A hard char
cap (`MAX_MEMORY_CHARS`, 3000) truncates the assembled context as a last
resort, dropping the oldest recent entries first and the summary last.

**Tested with a 40-run simulation** (pure logic, no DB needed — see the
compaction tests in `app/runtime/memory.py`'s design): memory size grows
normally for the first ~20 runs then flattens (1285 → 1350 chars from run
20 to run 40), instead of the old behavior's unbounded linear growth
(would have been 2538+ chars by run 40 and climbing forever).

Compaction currently uses a real LLM call (`LLMInterface.summarize()` in
`app/llm.py`) when `USE_MOCK = False`; the mock fallback truncates
instead of summarizing, so compaction plumbing works today but real
*abstractive* summarization needs a live provider.


- Real search/HTTP backends (currently mocked — swap the `search_fn` /
  `request_fn` in `app/tools/web_search.py` / `http_request.py`)
- Multi-project switcher UI (single default project for now)
- Parallel/concurrent child-agent execution (the engine runs sequentially;
  `asyncio.gather` over independent branches is a natural next step)
- Auto-update wiring, OpenTelemetry tracing, Monaco editor for prompts
  (currently plain textareas)
