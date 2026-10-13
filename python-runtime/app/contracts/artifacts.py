"""Universal, modality-neutral artifact contracts.

Artifacts may represent a single file or a structured project. The core stores
opaque bytes plus metadata; domain adapters interpret and validate the payload.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field, field_validator


class ArtifactRecord(BaseModel):
    """Current immutable-version pointer and descriptive metadata for an artifact."""

    artifact_id: str
    project_id: str
    artifact_type: str
    name: str
    media_type: str = "application/octet-stream"
    version: int = Field(ge=1)
    sha256: str
    size_bytes: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    change_summary: str = "Created"
    created_at: datetime
    updated_at: datetime


class ArtifactVersion(BaseModel):
    """Immutable content version; version history is append-only."""

    artifact_id: str
    version: int = Field(ge=1)
    sha256: str
    size_bytes: int = Field(ge=0)
    media_type: str = "application/octet-stream"
    metadata: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    change_summary: str
    created_at: datetime


class ArtifactPayload(BaseModel):
    record: ArtifactRecord
    content: bytes


class ArtifactChange(BaseModel):
    artifact_id: str
    from_version: int | None = None
    to_version: int
    operation: str
    summary: str
    actor: str = "system"
    created_at: datetime


class ArtifactCreate(BaseModel):
    project_id: str
    artifact_type: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=500)
    media_type: str = "application/octet-stream"
    metadata: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)

    @field_validator("artifact_type", "name", "media_type")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Value must not be blank.")
        return value.strip()


class ArtifactUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    change_summary: str = Field(min_length=1, max_length=2_000)
    media_type: str | None = None
    metadata: dict[str, Any] | None = None
    dependencies: list[str] | None = None


class ArtifactStore(Protocol):
    """Persistence contract consumed by platform adapters and capability tools."""

    def create(
        self,
        spec: ArtifactCreate,
        content: bytes,
        *,
        actor: str = "system",
    ) -> ArtifactRecord: ...

    def get(self, artifact_id: str) -> ArtifactRecord | None: ...

    def read(self, artifact_id: str, version: int | None = None) -> ArtifactPayload | None: ...

    def update(
        self,
        artifact_id: str,
        content: bytes,
        update: ArtifactUpdate,
        *,
        actor: str = "system",
    ) -> ArtifactRecord: ...

    def list_project(self, project_id: str, *, limit: int = 100, offset: int = 0) -> list[ArtifactRecord]: ...

    def history(self, artifact_id: str) -> list[ArtifactVersion]: ...

    def changes(self, artifact_id: str, *, limit: int = 100) -> list[ArtifactChange]: ...

    def verify_integrity(self, artifact_id: str, version: int | None = None) -> bool: ...
