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
| 2 | Tool Library: general-purpose (web/python/fs/http) + 45-tool Tier-1 production catalog (`app/tools/`) | **44 of 45 production tools run and tested locally** (see the Tier-1 catalog section below for the full breakdown). Web search / HTTP use real backends now (per your httpx/DDGS changes); `character_rig` is a deliberate stub. |
| 3 | Design system + Agent Tree/Editor/shelved Tool Catalog UI (`src/components/`) | Built, including the new `ToolCatalogModal.tsx` shelf picker. Needs `npm install` + `npm run dev` to verify visually. |
| 4 | LLM interface, LiteLLM-ready (`app/llm.py`) | Built with a mock fallback (`USE_MOCK = True`) since this sandbox has no network to call a real provider. |
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
uv run python main.py     # sanity check: http://127.0.0.1:8756/health
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
You should get: Vite on :5173 → Electron window → Python sidecar spawns →
UI bootstraps a default project → Agent Tree/Editor/Execution panels render.

### 4. Build Distributable Package
```bash
npm run dist
```
Produces the installer / application bundle inside `dist-electron/`.
