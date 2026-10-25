"""SQLite-backed, append-only artifact versions with content-addressed storage.

The store is deliberately independent of FastAPI and SQLAlchemy so the newer
RunnerCore and future application adapters can use it without coupling.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.contracts.artifacts import (
    ArtifactChange,
    ArtifactCreate,
    ArtifactPayload,
    ArtifactRecord,
    ArtifactUpdate,
    ArtifactVersion,
)


class ArtifactStoreError(RuntimeError):
    """Base class for artifact persistence failures."""


class ArtifactNotFound(ArtifactStoreError):
    pass


class ArtifactVersionConflict(ArtifactStoreError):
    """Raised when a write was based on a stale artifact version."""


class InvalidArtifactDependency(ArtifactStoreError):
    pass


_CHUNK_BYTES = 1024 * 1024


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class SQLiteArtifactStore:
    """Persistent registry and immutable content store rooted at one workspace.

    Content blobs are keyed by SHA-256. SQLite transactions serialize version
    allocation and optimistic concurrency checks. Old versions are never overwritten.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.state_root = self.root / ".agentforge" / "artifacts"
        self.objects_root = self.state_root / "objects"
        self.objects_root.mkdir(parents=True, exist_ok=True)
        self.database_path = self.state_root / "registry.sqlite3"
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.database_path), timeout=15.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            with connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS artifacts (
                        artifact_id TEXT PRIMARY KEY,
                        project_id TEXT NOT NULL,
                        artifact_type TEXT NOT NULL,
                        name TEXT NOT NULL,
                        media_type TEXT NOT NULL,
                        current_version INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_artifacts_project
                        ON artifacts(project_id, updated_at DESC);
                    CREATE TABLE IF NOT EXISTS artifact_versions (
                        artifact_id TEXT NOT NULL,
                        version INTEGER NOT NULL,
                        sha256 TEXT NOT NULL,
                        size_bytes INTEGER NOT NULL,
                        media_type TEXT NOT NULL,
                        metadata_json TEXT NOT NULL,
                        dependencies_json TEXT NOT NULL,
                        change_summary TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        PRIMARY KEY (artifact_id, version),
                        FOREIGN KEY (artifact_id) REFERENCES artifacts(artifact_id)
                    );
                    CREATE TABLE IF NOT EXISTS artifact_changes (
                        change_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        artifact_id TEXT NOT NULL,
                        from_version INTEGER,
                        to_version INTEGER NOT NULL,
                        operation TEXT NOT NULL,
                        summary TEXT NOT NULL,
                        actor TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (artifact_id) REFERENCES artifacts(artifact_id)
                    );
                    """
                )

    def _blob_path(self, digest: str) -> Path:
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ArtifactStoreError("Invalid content digest.")
        return self.objects_root / digest[:2] / digest[2:]

    def _store_blob(self, content: bytes) -> str:
        if not isinstance(content, bytes):
            raise TypeError("Artifact content must be bytes.")
        digest = hashlib.sha256(content).hexdigest()
        target = self._blob_path(digest)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            return digest
        fd, temporary = tempfile.mkstemp(prefix=".artifact-", dir=str(target.parent))
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.replace(temporary, target)
            except OSError:
                # Another writer may have installed the same digest concurrently.
                if not target.exists():
                    raise
                os.unlink(temporary)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return digest

    def _store_blob_file(self, source: Path) -> tuple[str, int]:
        """Copy a file into content-addressed storage without loading it into memory."""
        digest = hashlib.sha256()
        size = 0
        fd, temporary = tempfile.mkstemp(prefix=".artifact-", dir=str(self.objects_root))
        try:
            with open(source, "rb") as src, os.fdopen(fd, "wb") as dst:
                for chunk in iter(lambda: src.read(_CHUNK_BYTES), b""):
                    digest.update(chunk)
                    size += len(chunk)
                    dst.write(chunk)
                dst.flush()
                os.fsync(dst.fileno())
            hex_digest = digest.hexdigest()
            target = self._blob_path(hex_digest)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                try:
                    os.replace(temporary, target)
                except OSError:
                    if not target.exists():
                        raise
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return hex_digest, size

    def _blob_matches(self, digest: str) -> bool:
        try:
            with open(self._blob_path(digest), "rb") as stream:
                actual = hashlib.sha256()
                for chunk in iter(lambda: stream.read(_CHUNK_BYTES), b""):
                    actual.update(chunk)
        except OSError:
            return False
        return actual.hexdigest() == digest

    @staticmethod
    def _record(row: sqlite3.Row, version: sqlite3.Row) -> ArtifactRecord:
        return ArtifactRecord(
            artifact_id=row["artifact_id"],
            project_id=row["project_id"],
            artifact_type=row["artifact_type"],
            name=row["name"],
            media_type=version["media_type"],
            version=version["version"],
            sha256=version["sha256"],
            size_bytes=version["size_bytes"],
            metadata=json.loads(version["metadata_json"]),
            dependencies=json.loads(version["dependencies_json"]),
            change_summary=version["change_summary"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(version["created_at"]),
        )

    @staticmethod
    def _version(row: sqlite3.Row) -> ArtifactVersion:
        return ArtifactVersion(
            artifact_id=row["artifact_id"],
            version=row["version"],
            sha256=row["sha256"],
            size_bytes=row["size_bytes"],
            media_type=row["media_type"],
            metadata=json.loads(row["metadata_json"]),
            dependencies=json.loads(row["dependencies_json"]),
            change_summary=row["change_summary"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def _validate_dependencies(
        self,
        connection: sqlite3.Connection,
        project_id: str,
        dependencies: list[str],
        artifact_id: str | None = None,
    ) -> None:
        deps = list(dict.fromkeys(dependencies))
        if len(deps) != len(dependencies):
            raise InvalidArtifactDependency("Duplicate artifact dependencies are not allowed.")
        if artifact_id and artifact_id in deps:
            raise InvalidArtifactDependency("An artifact cannot depend on itself.")
        if not deps:
            return
        placeholders = ",".join("?" for _ in deps)
        rows = connection.execute(
            f"SELECT artifact_id, project_id, current_version FROM artifacts WHERE artifact_id IN ({placeholders})",
            deps,
        ).fetchall()
        found = {row["artifact_id"]: row for row in rows}
        missing = sorted(set(deps) - set(found))
        if missing:
            raise InvalidArtifactDependency(f"Unknown artifact dependencies: {missing}")
        wrong_project = [dep for dep in deps if found[dep]["project_id"] != project_id]
        if wrong_project:
            raise InvalidArtifactDependency("Dependencies must belong to the same project.")

        # Prevent cycles through the current dependency graph.
        if artifact_id:
            visited: set[str] = set()
            stack = list(deps)
            while stack:
                candidate = stack.pop()
                if candidate == artifact_id:
                    raise InvalidArtifactDependency("Artifact dependencies cannot contain a cycle.")
                if candidate in visited:
                    continue
                visited.add(candidate)
                row = connection.execute(
                    "SELECT dependencies_json FROM artifact_versions WHERE artifact_id=? AND version=("
                    "SELECT current_version FROM artifacts WHERE artifact_id=?)",
                    (candidate, candidate),
                ).fetchone()
                if row:
                    stack.extend(json.loads(row["dependencies_json"]))

    def create(self, spec: ArtifactCreate, content: bytes, *, actor: str = "system") -> ArtifactRecord:
        return self._create(spec, self._store_blob(content), len(content), actor=actor)

    def create_from_file(self, spec: ArtifactCreate, source: str | Path, *, actor: str = "system") -> ArtifactRecord:
        """Like create(), but streams the content from a file (for large media)."""
        digest, size = self._store_blob_file(Path(source))
        return self._create(spec, digest, size, actor=actor)

    def _create(self, spec: ArtifactCreate, digest: str, size: int, *, actor: str) -> ArtifactRecord:
        artifact_id = str(uuid.uuid4())
        now = _now()
        dependencies = list(spec.dependencies)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._validate_dependencies(connection, spec.project_id, dependencies)
            connection.execute(
                "INSERT INTO artifacts VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (artifact_id, spec.project_id, spec.artifact_type, spec.name, spec.media_type,
                 1, now.isoformat(), now.isoformat()),
            )
            connection.execute(
                "INSERT INTO artifact_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (artifact_id, 1, digest, size, spec.media_type, _json(spec.metadata),
                 _json(dependencies), "Created", now.isoformat()),
            )
            connection.execute(
                "INSERT INTO artifact_changes(artifact_id, from_version, to_version, operation, summary, actor, created_at) "
                "VALUES (?, NULL, 1, 'create', 'Created', ?, ?)",
                (artifact_id, actor[:200], now.isoformat()),
            )
            connection.commit()
        record = self.get(artifact_id)
        assert record is not None
        return record

    def get(self, artifact_id: str) -> ArtifactRecord | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM artifacts WHERE artifact_id=?", (artifact_id,)).fetchone()
            if not row:
                return None
            version = connection.execute(
                "SELECT * FROM artifact_versions WHERE artifact_id=? AND version=?",
                (artifact_id, row["current_version"]),
            ).fetchone()
            return self._record(row, version) if version else None

    def read(self, artifact_id: str, version: int | None = None) -> ArtifactPayload | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM artifacts WHERE artifact_id=?", (artifact_id,)).fetchone()
            if not row:
                return None
            requested_version = version if version is not None else row["current_version"]
            version_row = connection.execute(
                "SELECT * FROM artifact_versions WHERE artifact_id=? AND version=?",
                (artifact_id, requested_version),
            ).fetchone()
            if not version_row:
                return None
            record = self._record(row, version_row)
            blob_path = self._blob_path(version_row["sha256"])
            try:
                content = blob_path.read_bytes()
            except OSError as exc:
                raise ArtifactStoreError(f"Artifact content is unavailable for {artifact_id} version {requested_version}.") from exc
            if hashlib.sha256(content).hexdigest() != version_row["sha256"]:
                raise ArtifactStoreError(f"Artifact integrity check failed for {artifact_id} version {requested_version}.")
            return ArtifactPayload(record=record, content=content)

    def update(
        self,
        artifact_id: str,
        content: bytes,
        update: ArtifactUpdate,
        *,
        actor: str = "system",
    ) -> ArtifactRecord:
        digest = self._store_blob(content)
        now = _now()
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT * FROM artifacts WHERE artifact_id=?", (artifact_id,)
            ).fetchone()
            if not current:
                connection.rollback()
                raise ArtifactNotFound(artifact_id)
            if current["current_version"] != update.expected_version:
                connection.rollback()
                raise ArtifactVersionConflict(
                    f"Expected version {update.expected_version}, current version is {current['current_version']}."
                )
            previous = connection.execute(
                "SELECT * FROM artifact_versions WHERE artifact_id=? AND version=?",
                (artifact_id, current["current_version"]),
            ).fetchone()
            metadata = update.metadata if update.metadata is not None else json.loads(previous["metadata_json"])
            dependencies = update.dependencies if update.dependencies is not None else json.loads(previous["dependencies_json"])
            self._validate_dependencies(connection, current["project_id"], dependencies, artifact_id)
            media_type = update.media_type or previous["media_type"]
            new_version = current["current_version"] + 1
            summary = update.change_summary.strip()
            if not summary:
                connection.rollback()
                raise ValueError("change_summary must not be blank.")
            connection.execute(
                "INSERT INTO artifact_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (artifact_id, new_version, digest, len(content), media_type, _json(metadata),
                 _json(dependencies), summary, now.isoformat()),
            )
            connection.execute(
                "UPDATE artifacts SET media_type=?, current_version=?, updated_at=? WHERE artifact_id=?",
                (media_type, new_version, now.isoformat(), artifact_id),
            )
            connection.execute(
                "INSERT INTO artifact_changes(artifact_id, from_version, to_version, operation, summary, actor, created_at) "
                "VALUES (?, ?, ?, 'update', ?, ?, ?)",
                (artifact_id, current["current_version"], new_version, summary, actor[:200], now.isoformat()),
            )
            connection.commit()
        record = self.get(artifact_id)
        assert record is not None
        return record

    def list_project(self, project_id: str, *, limit: int = 100, offset: int = 0) -> list[ArtifactRecord]:
        limit = min(500, max(1, int(limit)))
        offset = max(0, int(offset))
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM artifacts WHERE project_id=? ORDER BY updated_at DESC, artifact_id LIMIT ? OFFSET ?",
                (project_id, limit, offset),
            ).fetchall()
            result = []
            for row in rows:
                version = connection.execute(
                    "SELECT * FROM artifact_versions WHERE artifact_id=? AND version=?",
                    (row["artifact_id"], row["current_version"]),
                ).fetchone()
                if version:
                    result.append(self._record(row, version))
            return result

    def history(self, artifact_id: str) -> list[ArtifactVersion]:
        with closing(self._connect()) as connection:
            if not connection.execute("SELECT 1 FROM artifacts WHERE artifact_id=?", (artifact_id,)).fetchone():
                return []
            rows = connection.execute(
                "SELECT * FROM artifact_versions WHERE artifact_id=? ORDER BY version ASC", (artifact_id,)
            ).fetchall()
            return [self._version(row) for row in rows]

    def changes(self, artifact_id: str, *, limit: int = 100) -> list[ArtifactChange]:
        limit = min(500, max(1, int(limit)))
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM artifact_changes WHERE artifact_id=? ORDER BY change_id DESC LIMIT ?",
                (artifact_id, limit),
            ).fetchall()
            return [
                ArtifactChange(
                    artifact_id=row["artifact_id"],
                    from_version=row["from_version"],
                    to_version=row["to_version"],
                    operation=row["operation"],
                    summary=row["summary"],
                    actor=row["actor"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                for row in rows
            ]

    def verify_integrity(self, artifact_id: str, version: int | None = None) -> bool:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT current_version FROM artifacts WHERE artifact_id=?", (artifact_id,)).fetchone()
            if not row:
                return False
            requested_version = version if version is not None else row["current_version"]
            version_row = connection.execute(
                "SELECT sha256 FROM artifact_versions WHERE artifact_id=? AND version=?",
                (artifact_id, requested_version),
            ).fetchone()
            if not version_row:
                return False
            return self._blob_matches(version_row["sha256"])

    def open_verified(self, artifact_id: str, version: int | None = None) -> tuple[ArtifactRecord, Path] | None:
        """Return (record, blob path) after a streamed integrity check, for file responses."""
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM artifacts WHERE artifact_id=?", (artifact_id,)).fetchone()
            if not row:
                return None
            requested_version = version if version is not None else row["current_version"]
            version_row = connection.execute(
                "SELECT * FROM artifact_versions WHERE artifact_id=? AND version=?",
                (artifact_id, requested_version),
            ).fetchone()
            if not version_row:
                return None
            record = self._record(row, version_row)
        if not self._blob_matches(record.sha256):
            raise ArtifactStoreError(f"Artifact integrity check failed for {artifact_id} version {requested_version}.")
        return record, self._blob_path(record.sha256)
