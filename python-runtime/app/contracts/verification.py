"""Common verification contracts; modality-specific checks plug into this interface."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

VerificationStatus = Literal["passed", "failed", "needs_review", "skipped"]
CheckStatus = Literal["passed", "failed", "warning"]


class VerificationCheck(BaseModel):
    check_id: str
    status: CheckStatus
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)


class VerificationReport(BaseModel):
    artifact_id: str
    artifact_version: int
    status: VerificationStatus
    checks: list[VerificationCheck] = Field(default_factory=list)
    summary: str = ""
    verifier: str = "unassigned"
    verified_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactVerifier(Protocol):
    """A verifier validates one artifact type without mutating the artifact."""

    name: str

    async def verify(self, artifact: Any, context: dict[str, Any]) -> VerificationReport: ...
