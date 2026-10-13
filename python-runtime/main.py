"""
AgentForge Python runtime entry point.
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.db import init_db
from app.infra.auth import TokenAuthMiddleware, require_runtime_token
from app.routers import agents, executions, executions_v2, projects, settings, tools
from app.routers import catalog as catalog_router
from app.services.executions import manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agentforge")

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing AgentForge database...")
    init_db()
    interrupted = manager.mark_running_interrupted()
    logger.info("Database initialized successfully; marked %s stale runs interrupted.", interrupted)
    yield
    await manager.shutdown()

app = FastAPI(title="AgentForge Runtime", lifespan=lifespan)
app.include_router(projects.router)
app.include_router(agents.router)
app.include_router(tools.router)
app.include_router(executions.router)
app.include_router(executions_v2.router)
app.include_router(catalog_router.router)
app.include_router(settings.router)

@app.get("/files/{relpath:path}", tags=["legacy-files"])
def get_legacy_file(relpath: str):
    """Authenticated compatibility route for older output artifacts.

    Do not mount StaticFiles here: active HTML/SVG/JS artifacts must never execute
    on the sidecar origin, even when a caller possesses a valid query token.
    """
    from app.infra.workspace import RunWorkspace
    from app.tools.base import ToolExecutionError

    try:
        path = RunWorkspace("legacy-files", root=OUTPUT_DIR).resolve(relpath)
    except (ToolExecutionError, ValueError, OSError) as exc:
        raise HTTPException(status_code=404, detail="File not found") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    headers = {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox",
    }
    if path.suffix.lower() in {".html", ".htm", ".svg", ".js", ".mjs", ".xml", ".xhtml", ".xsl"}:
        headers["Content-Disposition"] = "attachment"
    return FileResponse(path=path, headers=headers)

app.add_middleware(TokenAuthMiddleware)

# Add CORS outside authentication so browser preflights are answered correctly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "null"],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=False,
)


@app.get("/health")
def health() -> dict:
    # "fake" = built-in test runner (placeholder replies); "v2" = real models via LiteLLM.
    return {"status": "ok", "runner": os.environ.get("AGENTFORGE_RUNNER", "fake")}


def main() -> None:
    import sys

    require_runtime_token()
  
    port = 0
    if "PORT" in os.environ:
        try:
            port = int(os.environ["PORT"])
        except ValueError:
            port = 0
    elif len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            port = 0

    if port == 0:
    # Default development port
      port = 8000

    # The outbound HTTP guard checks against this exact runtime port.
    os.environ["AGENTFORGE_PORT"] = str(port)

    # Announce ready port for parent Electron process
    print(f"AGENTFORGE_READY:{port}", flush=True)
    logger.info(f"AGENTFORGE_READY:{port}")

    # Query-string tokens are used only for WebSocket/file URLs. Disable access logs so
    # these URLs are never copied into stdout or Electron's forwarded runtime log.
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info", access_log=False)


if __name__ == "__main__":
    main()
