"""Execution-lifecycle adapter for durable artifacts and verification.

Keeps RunnerCore independent from the legacy SQLAlchemy ExecutionEngine while
making files and final outputs durable in the run workspace.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.contracts.artifacts import ArtifactCreate, ArtifactRecord
from app.contracts.verification import VerificationReport
from app.core.artifact_store import SQLiteArtifactStore
from app.core.verification import VerificationEngine


class ExecutionArtifactLifecycle:
    """Persist workspace outputs and run final text, then record verification."""

    def __init__(self, workspace_root: str | Path, project_id: str):
        self.root = Path(workspace_root).resolve()
        self.project_id = project_id
        self.store = SQLiteArtifactStore(self.root)
        self.verification = VerificationEngine()

    async def persist(
        self,
        *,
        name: str,
        artifact_type: str,
        content: bytes,
        media_type: str = "application/octet-stream",
        metadata: dict[str, Any] | None = None,
    ) -> tuple[ArtifactRecord, VerificationReport]:
        record = self.store.create(
            ArtifactCreate(
                project_id=self.project_id,
                artifact_type=artifact_type,
                name=name,
                media_type=media_type,
                metadata=metadata or {},
            ),
            content,
            actor="runner",
        )
        payload = self.store.read(record.artifact_id, record.version)
        if payload is None:
            raise RuntimeError(f"Persisted artifact {record.artifact_id} could not be read back.")
        report = await self.verification.verify(
            payload,
            context={"project_id": self.project_id, "workspace_root": str(self.root)},
        )
        return record, report

    async def persist_workspace_file(
        self,
        workspace: Any,
        *,
        path: str,
        media_type: str | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[ArtifactRecord, VerificationReport]:
        # Resolve through the workspace's path guard; never read arbitrary paths.
        target = workspace.resolve(path)
        if not target.is_file():
            raise FileNotFoundError(f"Artifact path does not point to a file: {path}")
        combined_metadata = dict(metadata or {})
        if description:
            combined_metadata["description"] = description
        combined_metadata["workspace_path"] = workspace.relative(target)
        spec = ArtifactCreate(
            project_id=self.project_id,
            artifact_type="tool_artifact",
            name=target.name,
            media_type=media_type or "application/octet-stream",
            metadata=combined_metadata,
        )
        # Stream into the store: tool files can be large videos.
        record = self.store.create_from_file(spec, target, actor="runner")
        if not self.verification.supports(record.artifact_type):
            return record, VerificationReport(
                artifact_id=record.artifact_id,
                artifact_version=record.version,
                status="skipped",
                summary=f"No verifier registered for artifact type '{record.artifact_type}'.",
                verifier="none",
            )
        payload = self.store.read(record.artifact_id, record.version)
        if payload is None:
            raise RuntimeError(f"Persisted artifact {record.artifact_id} could not be read back.")
        report = await self.verification.verify(
            payload,
            context={"project_id": self.project_id, "workspace_root": str(self.root)},
        )
        return record, report
