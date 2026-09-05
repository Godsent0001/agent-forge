"""
AgentForge Python runtime entry point.

This is what the Tauri sidecar spawns. For Phase 0 it just proves the
pipeline works end to end: Tauri launches this process, it binds to a
fixed local port, and the React frontend can reach it.

Real agent/tool/execution logic gets layered on in later phases —
nothing about the recursive runtime lives here yet.
"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import init_db
from app.routers import agents, executions, projects, tools
from app.routers import catalog as catalog_router

app = FastAPI(title="AgentForge Runtime")
app.include_router(projects.router)
app.include_router(agents.router)
app.include_router(tools.router)
app.include_router(executions.router)
app.include_router(catalog_router.router)

# The frontend is served from a Tauri webview, not a normal browser origin,
# so CORS needs to explicitly allow the dev server / tauri origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this before shipping past Phase 0
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def main() -> None:
    # Fixed port so the frontend doesn't need service discovery in Phase 0.
    # 127.0.0.1 only — never 0.0.0.0 — this must stay local-machine-only.
    uvicorn.run(app, host="127.0.0.1", port=8756, log_level="info")


if __name__ == "__main__":
    main()
