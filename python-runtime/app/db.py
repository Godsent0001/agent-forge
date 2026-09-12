"""
Database setup. SQLite is the source of truth (per the spec: this is a
local desktop app, no Mongo/Redis/cloud infra in V1).

Schema changes go through Alembic migrations (see alembic/), not
create_all() in production — create_all() here is only a Phase-0
convenience until the first migration exists.
"""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Lives next to the executable in production; for now, relative to this file.
DB_PATH = Path(__file__).resolve().parent.parent / "agentforge.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    # Import models here so they're registered on Base.metadata before
    # create_all runs, without creating an import cycle.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    # Lightweight migration check for existing databases
    with engine.connect() as conn:
        from sqlalchemy import inspect, text
        inspector = inspect(conn)
        if "agents" in inspector.get_table_names():
            columns = [c["name"] for c in inspector.get_columns("agents")]
            if "learned_experience" not in columns:
                conn.execute(text("ALTER TABLE agents ADD COLUMN learned_experience TEXT DEFAULT ''"))
                conn.commit()
