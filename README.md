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
| 0 | Electron + React + FastAPI scaffold, sidecar wiring | Built. Needs local `npm run dev` to verify. |
| 1 | Full data model + cycle/depth validation (`app/models.py`, `app/graph.py`) | Schema built; cycle-detection **algorithm unit-tested and passing** (6/6 cases). Full DB/API needs `uv sync` locally (no network here to install SQLAlchemy). |
| 2 | Tool Library: general-purpose (web/python/fs/http) + 45-tool Tier-1 production catalog (`app/tools/`) | **production tool catalog is implemented and tested locally** (see the Tier-1 catalog section below for the full breakdown). Web search / HTTP use real backends now (per your httpx/DDGS changes); `character_rig` is implemented as part of the current runtime. |
| 3 | Design system + Agent Tree/Editor/shelved Tool Catalog UI (`src/components/`) | Built, including the new `ToolCatalogModal.tsx` shelf picker. Needs `npm install` + `npm run dev` to verify visually. |
| 4 | LLM adapter over LiteLLM (`app/core/llm/`) | Typed errors, retries, pricing from LiteLLM's model table. |
| 5/6 | Agent loop + recursive execution (`app/core/runner.py`, RunnerCore) | The only execution engine; the original prototype engine and spike were removed (S-04). |
| 7 | WebSocket live execution events (`app/ws.py`, `src/hooks/useExecutionStream.ts`) | Built. Needs local run to verify the live tree UI. |
| 8 | Design polish: fonts, scrollbars, focus states, motion | Built into `src/index.css` and `tailwind.config.js`. |
| 9 | Packaging: standalone Python sidecar, OS-keychain API key storage | Built (`electron/main.js` using `safeStorage` + `src/components/SettingsModal.tsx`). |

---

## Setup & Running

### Prerequisites
- Node.js 18+, npm
- [`uv`](https://docs.astral.sh/uv/)

### 1. Frontend & Electron
```bash
npm install
```

### 2. Python runtime
```bash
cd python-runtime
uv python install 3.11
uv venv --python 3.11
uv sync
# The runtime now requires a bearer token. For a standalone local dev server:
# macOS/Linux:
AGENTFORGE_DEV=1 uv run python main.py
# Windows PowerShell:
# $env:AGENTFORGE_DEV="1"; uv run python main.py
# Health check: http://127.0.0.1:8000/health
```

Initialize the DB schema:
```bash
uv run alembic revision --autogenerate -m "initial schema"
uv run alembic upgrade head
```

### 3. Run Development App
```bash
npm run dev
```

Electron generates a per-launch random bearer token and passes it only to the
local sidecar and isolated renderer. Browser-only development must explicitly
opt into the development token in both places: set `AGENTFORGE_DEV=1` for the
runtime and add `VITE_DEV_TOKEN=dev` plus `VITE_API_BASE=http://127.0.0.1:8000`
to `.env.local`. Do not use that fixed token outside local development. Ordinary API routes require `Authorization: Bearer …`;
only WebSocket streams and generated-file URLs accept a query token.
You should get: Vite on :5173 → Electron window → Python sidecar spawns →
UI bootstraps a default project → Agent Tree/Editor/Execution panels render.

### 4. Build Distributable Package
```bash
npm run dist
```
Produces the installer / application bundle inside `dist-electron/`.


## Documentation

See [`docs/`](docs/) for project plans, contracts, task cards, and testing guidance.

### Video clips without watching the video

The Video pack includes `video_transcript`, `clip_finder` and `clip_extractor`. Together
they find moments in long videos from timestamped captions (local Whisper fallback), then
download only those sections. That costs a few thousand tokens per video instead of about
1M per hour of footage. See [`docs/VIDEO-CLIPS.md`](docs/VIDEO-CLIPS.md). Requires
`ffmpeg` on PATH for cutting; `uv sync --extra transcribe` enables speech-to-text for
videos that have no captions.

## RunnerCore and model configuration

The application uses **RunnerCore by default** for both the established `/executions` API and `/v2/executions`. Normal startup therefore uses the selected agent's configured model and requires valid provider credentials before real model calls can succeed.

1. Open **Provider settings** and save a key for the provider you want (keys stay on your device and are re-applied to the runtime at every start).
2. Pick the provider and model on the agent. Any model your provider offers can be used through **Custom model ID**.
3. For a local development session, `npm run dev` and `npm run dev:live` both use RunnerCore; `dev:live` explicitly sets `AGENTFORGE_RUNNER=v2`.

For deterministic simulation/tests only, explicitly set `AGENTFORGE_RUNNER=fake`; this uses the placeholder FakeRunner and is not the normal application execution path. Do not use that override when validating real model execution.

Models are routed through LiteLLM as `<provider>/<model>`. Providers listed in `src/config/providers.ts` need the matching key handled by the runtime (`app/routers/settings.py`).

Chat history is saved locally (last 300 messages per agent) and each reply links to its run log, which can be exported as JSON from the run panel.
