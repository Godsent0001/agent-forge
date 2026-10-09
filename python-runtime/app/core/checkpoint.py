"""Versioned checkpoint schema and storage protocol for host-backed durable recovery."""
from __future__ import annotations
import asyncio
import sqlite3
from datetime import datetime,timezone
from pathlib import Path
from typing import Any,Protocol
from pydantic import BaseModel,Field

class AgentFrame(BaseModel):
    invocation_id:str
    agent_id:str
    parent_invocation_id:str|None=None
    task:str
    depth:int=0
    iteration:int=0
    messages:list[dict[str,Any]]=Field(default_factory=list)
    pending_tool_call_ids:list[str]=Field(default_factory=list)
    completed_tool_results:dict[str,str]=Field(default_factory=dict)

class ExecutionCheckpoint(BaseModel):
    schema_version:int=1
    execution_id:str
    graph_fingerprint:str
    status:str
    created_at:datetime=Field(default_factory=lambda:datetime.now(timezone.utc))
    updated_at:datetime=Field(default_factory=lambda:datetime.now(timezone.utc))
    frames:list[AgentFrame]=Field(default_factory=list)
    task_state:dict[str,Any]=Field(default_factory=dict)
    budget_state:dict[str,Any]=Field(default_factory=dict)
    artifact_refs:list[str]=Field(default_factory=list)
    metadata:dict[str,Any]=Field(default_factory=dict)

class CheckpointStore(Protocol):
    async def save(self,checkpoint:ExecutionCheckpoint)->None:...
    async def load(self,execution_id:str)->ExecutionCheckpoint|None:...
    async def delete(self,execution_id:str)->None:...

class InMemoryCheckpointStore:
    """For tests/dev only; not durable across process restarts."""
    def __init__(self):self._items={};self._lock=asyncio.Lock()
    async def save(self,checkpoint:ExecutionCheckpoint)->None:
        async with self._lock:self._items[checkpoint.execution_id]=checkpoint.model_copy(deep=True)
    async def load(self,execution_id:str)->ExecutionCheckpoint|None:
        async with self._lock:
            item=self._items.get(execution_id)
            return item.model_copy(deep=True) if item is not None else None
    async def delete(self,execution_id:str)->None:
        async with self._lock:self._items.pop(execution_id,None)


class SQLiteCheckpointStore:
    """Durable local checkpoint store.

    The host must still decide safe checkpoint boundaries and implement restoration
    of the runner's call stack. This store persists versioned snapshots transactionally;
    it does not by itself make an in-flight execution resumable.
    """
    def __init__(self, database_path: str | Path):
        self.database_path = str(database_path)
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.database_path, timeout=10.0)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS agent_checkpoints ("
                "execution_id TEXT PRIMARY KEY, schema_version INTEGER NOT NULL, "
                "updated_at TEXT NOT NULL, payload TEXT NOT NULL)"
            )

    async def save(self, checkpoint: ExecutionCheckpoint) -> None:
        await asyncio.to_thread(self._save_sync, checkpoint)

    def _save_sync(self, checkpoint: ExecutionCheckpoint) -> None:
        payload = checkpoint.model_dump_json()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO agent_checkpoints(execution_id, schema_version, updated_at, payload) "
                "VALUES (?, ?, ?, ?) ON CONFLICT(execution_id) DO UPDATE SET "
                "schema_version=excluded.schema_version, updated_at=excluded.updated_at, payload=excluded.payload",
                (checkpoint.execution_id, checkpoint.schema_version, checkpoint.updated_at.isoformat(), payload),
            )

    async def load(self, execution_id: str) -> ExecutionCheckpoint | None:
        return await asyncio.to_thread(self._load_sync, execution_id)

    def _load_sync(self, execution_id: str) -> ExecutionCheckpoint | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM agent_checkpoints WHERE execution_id = ?", (execution_id,)
            ).fetchone()
        return ExecutionCheckpoint.model_validate_json(row[0]) if row else None

    async def delete(self, execution_id: str) -> None:
        await asyncio.to_thread(self._delete_sync, execution_id)

    def _delete_sync(self, execution_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM agent_checkpoints WHERE execution_id = ?", (execution_id,))
