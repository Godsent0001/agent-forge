from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
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
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    agents: Mapped[list["Agent"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    tools: Mapped[list["Tool"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    executions: Mapped[list["Execution"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )


class Tool(Base):
    __tablename__ = "tools"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String, nullable=False)
    input_schema: Mapped[dict] = mapped_column(JSON, default=dict)
    output_schema: Mapped[dict] = mapped_column(JSON, default=dict)
    config: Mapped[dict] = mapped_column(JSON, default=dict)

    project: Mapped[Project] = relationship(back_populates="tools")


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    provider: Mapped[str] = mapped_column(String, default="anthropic")
    model: Mapped[str] = mapped_column(String, default="")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    tool_use_schema: Mapped[str] = mapped_column(Text, default="")
    memory_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    lessons_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    memory_summary: Mapped[str] = mapped_column(Text, default="")
    learned_experience: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    project: Mapped[Project] = relationship(back_populates="agents")
    tool_links: Mapped[list["AgentToolLink"]] = relationship(
        back_populates="agent",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="AgentToolLink.agent_id",
    )
    child_links: Mapped[list["AgentAgentLink"]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="AgentAgentLink.parent_agent_id",
    )
    parent_links: Mapped[list["AgentAgentLink"]] = relationship(
        back_populates="child",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="AgentAgentLink.child_agent_id",
    )
    memory_entries: Mapped[list["MemoryEntry"]] = relationship(
        back_populates="agent", cascade="all, delete-orphan", passive_deletes=True
    )


class AgentToolLink(Base):
    __tablename__ = "agent_tool_links"
    __table_args__ = (UniqueConstraint("agent_id", "tool_id", name="uq_agent_tool"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    tool_id: Mapped[str] = mapped_column(ForeignKey("tools.id", ondelete="CASCADE"))

    agent: Mapped[Agent] = relationship(back_populates="tool_links", foreign_keys=[agent_id])
    tool: Mapped[Tool] = relationship()


class AgentAgentLink(Base):
    __tablename__ = "agent_agent_links"
    __table_args__ = (
        UniqueConstraint("parent_agent_id", "child_agent_id", name="uq_agent_child"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    parent_agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    child_agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    description: Mapped[str] = mapped_column(Text, default="")

    parent: Mapped[Agent] = relationship(back_populates="child_links", foreign_keys=[parent_agent_id])
    child: Mapped[Agent] = relationship(back_populates="parent_links", foreign_keys=[child_agent_id])


class MemoryEntry(Base):
    __tablename__ = "memory_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String, default="fact")
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    source_type: Mapped[str] = mapped_column(String, default="user_stated")
    evidence: Mapped[str] = mapped_column(Text, default="")
    source_execution_id: Mapped[str | None] = mapped_column(
        ForeignKey("executions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    use_count: Mapped[int] = mapped_column(default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String, default="active")
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String, nullable=True)
    summarized: Mapped[bool] = mapped_column(Boolean, default=False)

    agent: Mapped[Agent] = relationship(back_populates="memory_entries")


class Execution(Base):
    __tablename__ = "executions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    root_agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    input_task: Mapped[str] = mapped_column(Text, default="")
    final_output: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="running")
    totals: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_graph_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    project: Mapped[Project] = relationship(back_populates="executions")
    events: Mapped[list["ExecutionEventRow"]] = relationship(
        back_populates="execution", cascade="all, delete-orphan", passive_deletes=True
    )


class ExecutionEventRow(Base):
    __tablename__ = "execution_events"
    __table_args__ = (
        Index("ix_execution_events_execution_seq", "execution_id", "seq"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    execution_id: Mapped[str] = mapped_column(ForeignKey("executions.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(nullable=False)
    span_id: Mapped[str | None] = mapped_column(String, nullable=True)
    parent_span_id: Mapped[str | None] = mapped_column(String, nullable=True)
    kind: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    type: Mapped[str] = mapped_column(String, nullable=False)
    agent_name: Mapped[str | None] = mapped_column(String, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String, nullable=True)
    depth: Mapped[int] = mapped_column(default=0)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_now)

    execution: Mapped[Execution] = relationship(back_populates="events")


Index("ix_memory_entries_agent_created", MemoryEntry.agent_id, MemoryEntry.created_at)



class Conversation(Base):
    """A persisted chat thread scoped to one project agent."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(160), default="New conversation", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)

    messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ConversationMessage.created_at",
    )


class ConversationMessage(Base):
    """Persisted user/assistant turn; tool cards remain part of the execution trace."""

    __tablename__ = "conversation_messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    execution_id: Mapped[str | None] = mapped_column(
        ForeignKey("executions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    feedback: Mapped["MessageFeedback | None"] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )


class MessageFeedback(Base):
    """One optional rating per assistant message."""

    __tablename__ = "message_feedback"

    message_id: Mapped[str] = mapped_column(
        ForeignKey("conversation_messages.id", ondelete="CASCADE"), primary_key=True
    )
    value: Mapped[int] = mapped_column(nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)

    message: Mapped[ConversationMessage] = relationship(back_populates="feedback")


Index(
    "ix_conversations_project_agent_created",
    Conversation.project_id,
    Conversation.agent_id,
    Conversation.created_at,
)
Index(
    "ix_conversation_messages_conversation_created",
    ConversationMessage.conversation_id,
    ConversationMessage.created_at,
)



class LessonEntry(Base):
    """Persistent user-reviewable lesson used to guide future agent runs."""

    __tablename__ = "lessons"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_execution_id: Mapped[str | None] = mapped_column(
        ForeignKey("executions.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String, default="active", nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)


Index("ix_memory_entries_agent_status_created", MemoryEntry.agent_id, MemoryEntry.status, MemoryEntry.created_at)
Index("ix_lessons_agent_status_created", LessonEntry.agent_id, LessonEntry.status, LessonEntry.created_at)


class ProjectAttachment(Base):
    """Opaque project attachment metadata; uploaded bytes are stored outside served roots."""

    __tablename__ = "attachments"
    __table_args__ = (
        Index("ix_attachments_project_created", "project_id", "created_at"),
        UniqueConstraint("storage_key", name="uq_attachments_storage_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    storage_key: Mapped[str] = mapped_column(String(64), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    declared_mime: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detected_mime: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="quarantined")
    scanner_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
