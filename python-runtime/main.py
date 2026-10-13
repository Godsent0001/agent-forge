"""
AgentForge Python runtime entry point.
"""

import runpy
import sys

# The frozen executable reuses this entry point to run one bounded Python snippet.
# Handle the flag before importing the application, FastAPI, or the database.
if len(sys.argv) >= 3 and sys.argv[1] == "--run-snippet":
    runpy.run_path(sys.argv[2], run_name="__main__")
    raise SystemExit(0)

import asyncio
import logging
import os
import socket
from contextlib import asynccontextmanager
from threading import Thread

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.db import init_db
from app.infra.auth import TokenAuthMiddleware, require_runtime_token
from app.infra.file_security import file_response_headers
from app.infra.paths import data_dir
from app.routers import (
    agents,
    executions,
    executions_v2,
    projects,
    settings,
    system,
    tools,
)
from app.routers import catalog as catalog_router
from app.routers import conversations as conversations_router
from app.routers import memory as memory_router
from app.services.executions import manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agentforge")

OUTPUT_DIR = data_dir() / "output"
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
app.include_router(conversations_router.router)
app.include_router(memory_router.router)
app.include_router(settings.router)
app.include_router(system.router)

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

    return FileResponse(path=path, headers=file_response_headers(path))

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


def _watch_parent_exit() -> None:
    if os.environ.get("AGENTFORGE_WATCH_PARENT") != "1":
        return

    def watch() -> None:
        try:
            sys.stdin.buffer.read()
        finally:
            # The Electron owner closed its pipe. Never leave a sidecar orphaned.
            os._exit(0)

    Thread(target=watch, name="parent-watchdog", daemon=True).start()


def _requested_port() -> int:
    raw = os.environ.get("PORT", "0")
    try:
        port = int(raw)
    except ValueError:
        return 0
    return port if 0 <= port <= 65535 else 0


def main() -> None:
    require_runtime_token()
    _watch_parent_exit()

    # Reserve the loopback port before passing it to uvicorn. Electron starts with
    # PORT=0 so competing app instances cannot collide on a fixed port.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", _requested_port()))
        sock.listen()
        port = int(sock.getsockname()[1])
        os.environ["AGENTFORGE_PORT"] = str(port)
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info", access_log=False)
        server = uvicorn.Server(config)

        async def serve() -> None:
            task = asyncio.create_task(server.serve(sockets=[sock]))
            while not server.started and not task.done():
                await asyncio.sleep(0.01)
            if server.started:
                print(f"AGENTFORGE_READY:{port}", flush=True)
                logger.info("AgentForge runtime is ready on loopback.")
            try:
                await task
            finally:
                sock.close()

        asyncio.run(serve())
    except BaseException:
        sock.close()
        raise


if __name__ == "__main__":
    main()
