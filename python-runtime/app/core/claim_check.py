"""Claim-Check Communication Protocol for AgentForge Core.

Implements TaskDirective and ClaimCheckEnvelope data models for scalable,
context-hygienic multi-agent delegation.
"""
from typing import Any, Literal
from pydantic import BaseModel, Field


class TaskDirective(BaseModel):
    """Downward task directive envelope passed from parent to child agent."""

    task_id: str
    sender_id: str
    recipient_id: str
    instruction: str
    assigned_skill: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    artifact_references: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(
        default_factory=lambda: {"max_iterations": 10, "timeout_sec": 300}
    )


class ClaimCheckSummary(BaseModel):
    """High-level summary card returned in Claim-Check envelope."""

    headline: str
    key_metrics: dict[str, Any] = Field(default_factory=dict)
    flags_or_warnings: list[str] = Field(default_factory=list)


class ClaimCheckEnvelope(BaseModel):
    """Upward response envelope containing summary card and URI pointers to full outputs."""

    task_id: str
    sender_id: str
    recipient_id: str
    status: Literal["COMPLETED", "FAILED", "NEEDS_REVIEW"]
    summary: ClaimCheckSummary
    result_artifact_uri: str
    execution_log_uri: str | None = None
