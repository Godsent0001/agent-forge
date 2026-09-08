"""
AgentForge Python runtime entry point.
"""

import logging
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import init_db
from app.routers import agents, executions, projects, settings, tools
from app.routers import catalog as catalog_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agentforge")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing AgentForge database...")
    init_db()
    logger.info("Database initialized successfully.")
    yield

app = FastAPI(title="AgentForge Runtime", lifespan=lifespan)
app.include_router(projects.router)
app.include_router(agents.router)
app.include_router(tools.router)
app.include_router(executions.router)
app.include_router(catalog_router.router)
app.include_router(settings.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def main() -> None:
    import sys
    import os
    import socket

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
        # Ask OS for a free localhost port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

    # Announce ready port for Tauri / parent process
    print(f"AGENTFORGE_READY:{port}", flush=True)
    logger.info(f"AGENTFORGE_READY:{port}")

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
