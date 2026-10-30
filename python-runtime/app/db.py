"""SQLite database setup and Alembic-backed schema initialization."""

import os
import sys
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from alembic import command
from app.infra.paths import data_dir

# Resolve the writable data root once, after Electron has supplied AGENTFORGE_DATA_DIR.
# Keep the database under that root in both development and packaged installs.
_DATA_ROOT = data_dir()
DB_PATH = Path(os.environ.get("AGENTFORGE_DB_PATH", str(_DATA_ROOT / "db" / "agentforge.db"))).expanduser().resolve()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DB_PATH}")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


@event.listens_for(Engine, "connect")
def set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    if dbapi_connection.__class__.__module__.split(".")[0] != "sqlite3":
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def init_db() -> None:
    from app import models  # noqa: F401

    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(cfg, "head")
