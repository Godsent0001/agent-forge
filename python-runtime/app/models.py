"""
Phase 1 — Core data model.

Project / Agent / Tool / AgentToolLink (junction enabling tool reuse) /
AgentAgentLink (junction enabling agent-as-tool) / Execution /
ExecutionEventRow / MemoryEntry.

Cycle detection lives in app/graph.py, not here — this file only defines
storage shape. Validation happens at the service layer before a row
is ever written.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, JSON, String, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    parallel_execution: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    agents: Mapped[list["Agent"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    tools: Mapped[list["Tool"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    executions: Mapped[list["Execution"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Tool(Base):
    """A normal, non-agent tool (Web Search, Python, File System, ...)."""

    __tablename__ = "tools"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String, nullable=False)  # "web_search" | "python" | "http_request" | ...
    input_schema: Mapped[dict] = mapped_column(JSON, default=dict)
    output_schema: Mapped[dict] = mapped_column(JSON, default=dict)
    config: Mapped[dict] = mapped_column(JSON, default=dict)

    project: Mapped[Project] = relationship(back_populates="tools")


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")

    provider: Mapped[str] = mapped_column(String, default="anthropic")
    model: Mapped[str] = mapped_column(String, default="")

    system_prompt: Mapped[str] = mapped_column(Text, default="")
    tool_use_schema: Mapped[str] = mapped_column(Text, default="")
    memory_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # Rolling summary of memory entries that have aged out of the verbatim
    # recent-window (see app/runtime/memory.py). Empty until enough history
    # accumulates to trigger the first compaction.
    memory_summary: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    project: Mapped[Project] = relationship(back_populates="agents")

    tool_links: Mapped[list["AgentToolLink"]] = relationship(
        back_populates="agent", cascade="all, delete-orphan", foreign_keys="AgentToolLink.agent_id"
    )
    child_links: Mapped[list["AgentAgentLink"]] = relationship(
        back_populates="parent", cascade="all, delete-orphan", foreign_keys="AgentAgentLink.parent_agent_id"
    )
    memory_entries: Mapped[list["MemoryEntry"]] = relationship(back_populates="agent", cascade="all, delete-orphan")


class AgentToolLink(Base):
    """Junction: agent -> normal tool. Many-to-many, tools are reused across agents."""

    __tablename__ = "agent_tool_links"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    tool_id: Mapped[str] = mapped_column(ForeignKey("tools.id"))

    agent: Mapped[Agent] = relationship(back_populates="tool_links", foreign_keys=[agent_id])
    tool: Mapped[Tool] = relationship()


class AgentAgentLink(Base):
    """
    Junction: parent agent -> child agent, i.e. 'child is available to parent
    as an agent-tool'. This is the edge cycle detection runs against.
    """

    __tablename__ = "agent_agent_links"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    parent_agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    child_agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    description: Mapped[str] = mapped_column(Text, default="")  # how the child is described as a tool

    parent: Mapped[Agent] = relationship(back_populates="child_links", foreign_keys=[parent_agent_id])
    child: Mapped[Agent] = relationship(foreign_keys=[child_agent_id])


class MemoryEntry(Base):
    __tablename__ = "memory_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    # True once this entry has been folded into Agent.memory_summary — it
    # stays in the table for provenance/future search, it just stops being
    # sent to the LLM verbatim.
    summarized: Mapped[bool] = mapped_column(Boolean, default=False)

    agent: Mapped[Agent] = relationship(back_populates="memory_entries")


class Execution(Base):
    __tablename__ = "executions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    root_agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    input_task: Mapped[str] = mapped_column(Text, default="")
    final_output: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="running")  # running | completed | error
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    project: Mapped[Project] = relationship(back_populates="executions")
    events: Mapped[list["ExecutionEventRow"]] = relationship(back_populates="execution", cascade="all, delete-orphan")


class ExecutionEventRow(Base):
    """Persisted copy of every ExecutionEvent, so the tree UI can be
    replayed after the fact, not just watched live."""

    __tablename__ = "execution_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    execution_id: Mapped[str] = mapped_column(ForeignKey("executions.id"))
    type: Mapped[str] = mapped_column(String, nullable=False)
    agent_name: Mapped[str | None] = mapped_column(String, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String, nullable=True)
    depth: Mapped[int] = mapped_column(default=0)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_now)

    execution: Mapped[Execution] = relationship(back_populates="events")
