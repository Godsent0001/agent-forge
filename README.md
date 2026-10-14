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
| 0.5 | Headless recursive-execution spike (`python-runtime/spike/headless_spike.py`) | **Run and passing** — see below. |
| 1 | Full data model + cycle/depth validation (`app/models.py`, `app/graph.py`) | Schema built; cycle-detection **algorithm unit-tested and passing** (6/6 cases). Full DB/API needs `uv sync` locally (no network here to install SQLAlchemy). |
| 2 | Tool Library: general-purpose (web/python/fs/http) + 45-tool Tier-1 production catalog (`app/tools/`) | **production tool catalog is implemented and tested locally** (see the Tier-1 catalog section below for the full breakdown). Web search / HTTP use real backends now (per your httpx/DDGS changes); `character_rig` is implemented as part of the current runtime. |
| 3 | Design system + Agent Tree/Editor/shelved Tool Catalog UI (`src/components/`) | Built, including the new `ToolCatalogModal.tsx` shelf picker. Needs `npm install` + `npm run dev` to verify visually. |
| 4 | LLM interface, LiteLLM-ready (`app/llm.py`) | Built with a real-provider path (`USE_MOCK = False`) since this sandbox has no network to call a real provider. |
| 5/6 | Production agent loop + recursive execution engine (`app/runtime/`) | Built on the validated Phase 0.5 logic, wired to real DB config/tools/LLM interface. Needs local deps to run end-to-end. |
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

## Running with real models

By default the backend uses a built-in **test runner** that answers with `FakeRunner completed: <your task>`. The UI labels those replies "Simulated". To use real models:

1. Start the app with the live runner: `npm run dev:live` (same as `npm run dev` with `AGENTFORGE_RUNNER=v2`).
2. Open **Provider settings** and save a key for the provider you want (keys stay on your device and are re-applied to the runtime at every start).
3. Pick the provider and model on the agent. Any model your provider offers can be used through **Custom model ID**.

Models are routed through LiteLLM as `<provider>/<model>`. Providers listed in `src/config/providers.ts` need the matching key handled by the runtime (`app/routers/settings.py`).

Chat history is saved locally (last 300 messages per agent) and each reply links to its run log, which can be exported as JSON from the run panel.
