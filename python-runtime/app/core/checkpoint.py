"""Versioned checkpoint schema and storage protocol for host-backed durable recovery."""
from __future__ import annotations
import asyncio
from datetime import datetime,timezone
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
    """For tests/dev only; a host must provide a durable implementation for restarts."""
    def __init__(self):self._items={};self._lock=asyncio.Lock()
    async def save(self,checkpoint:ExecutionCheckpoint)->None:
        async with self._lock:self._items[checkpoint.execution_id]=checkpoint.model_copy(deep=True)
    async def load(self,execution_id:str)->ExecutionCheckpoint|None:
        async with self._lock:
            item=self._items.get(execution_id)
            return item.model_copy(deep=True) if item is not None else None
    async def delete(self,execution_id:str)->None:
        async with self._lock:self._items.pop(execution_id,None)
