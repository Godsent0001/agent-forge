"""Durable, idempotent work queue for artifact and knowledge ingestion.

Jobs are stored in SQLite. Claims are atomic, expired leases are recovered,
and processors checkpoint a cursor after each bounded batch.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class IngestionJob:
    id: str
    kind: str
    content_hash: str
    payload: dict[str, Any]
    cursor: str | None
    status: str
    attempts: int
    max_attempts: int
    result: dict[str, Any] | None = None
    error: str | None = None


class IngestionQueue:
    """SQLite-backed queue with deduplication, leases, checkpoints and cancellation."""

    def __init__(self, database_path: str | Path, *, lease_seconds: int = 120, max_attempts: int = 5) -> None:
        if lease_seconds < 1 or max_attempts < 1:
            raise ValueError("lease_seconds and max_attempts must be positive")
        self.path = Path(database_path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS ingestion_jobs (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, content_hash TEXT NOT NULL,
                    payload TEXT NOT NULL, cursor TEXT, status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL,
                    available_at REAL NOT NULL, lease_until REAL, worker_id TEXT,
                    result TEXT, error TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL,
                    UNIQUE(kind, content_hash)
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_claim ON ingestion_jobs(status, available_at, created_at)")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=5000")
        return db

    @staticmethod
    def _job(row: sqlite3.Row) -> IngestionJob:
        return IngestionJob(
            id=row["id"], kind=row["kind"], content_hash=row["content_hash"],
            payload=json.loads(row["payload"]), cursor=row["cursor"],
            status=row["status"], attempts=row["attempts"],
            max_attempts=row["max_attempts"],
            result=json.loads(row["result"]) if row["result"] else None,
            error=row["error"],
        )

    def enqueue(self, kind: str, payload: dict[str, Any], *, content_hash: str | None = None, max_attempts: int | None = None) -> IngestionJob:
        """Create or return the existing job for the same kind and content hash."""
        if not kind or len(kind) > 80:
            raise ValueError("kind must contain 1 to 80 characters")
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = content_hash or hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        if len(digest) > 128:
            raise ValueError("content_hash is too long")
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                """INSERT OR IGNORE INTO ingestion_jobs
                   (id,kind,content_hash,payload,status,max_attempts,available_at,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), kind, digest, encoded, "queued", max_attempts or self.max_attempts, now, now, now),
            )
            row = db.execute("SELECT * FROM ingestion_jobs WHERE kind=? AND content_hash=?", (kind, digest)).fetchone()
            return self._job(row)

    def get(self, job_id: str) -> IngestionJob | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM ingestion_jobs WHERE id=?", (job_id,)).fetchone()
        return self._job(row) if row else None

    def claim(self, *, worker_id: str | None = None) -> IngestionJob | None:
        """Claim one available job and recover expired worker leases atomically."""
        now = time.time()
        worker = worker_id or str(uuid.uuid4())
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                """UPDATE ingestion_jobs SET
                     status=CASE WHEN attempts >= max_attempts THEN 'failed' ELSE 'queued' END,
                     worker_id=NULL, lease_until=NULL,
                     error=CASE WHEN attempts >= max_attempts THEN COALESCE(error, 'Worker lease expired; retry limit reached') ELSE error END,
                     available_at=?, updated_at=?
                   WHERE status='running' AND lease_until < ?""",
                (now, now, now),
            )
            row = db.execute(
                "SELECT * FROM ingestion_jobs WHERE status='queued' AND available_at <= ? ORDER BY created_at, id LIMIT 1",
                (now,),
            ).fetchone()
            if row is None:
                return None
            db.execute(
                """UPDATE ingestion_jobs SET status='running', attempts=attempts+1,
                   worker_id=?, lease_until=?, updated_at=? WHERE id=? AND status='queued'""",
                (worker, now + self.lease_seconds, now, row["id"]),
            )
            claimed = db.execute("SELECT * FROM ingestion_jobs WHERE id=?", (row["id"],)).fetchone()
            return self._job(claimed)

    def checkpoint(self, job_id: str, worker_id: str, cursor: str | None) -> bool:
        """Persist batch progress and renew the lease; reject stale workers."""
        now = time.time()
        with self._connect() as db:
            cur = db.execute(
                """UPDATE ingestion_jobs SET cursor=?, lease_until=?, updated_at=?
                   WHERE id=? AND status='running' AND worker_id=?""",
                (cursor, now + self.lease_seconds, now, job_id, worker_id),
            )
            return cur.rowcount == 1

    def complete(self, job_id: str, worker_id: str, result: dict[str, Any] | None = None) -> bool:
        now = time.time()
        with self._connect() as db:
            cur = db.execute(
                """UPDATE ingestion_jobs SET status='completed', result=?, error=NULL,
                   worker_id=NULL, lease_until=NULL, updated_at=?
                   WHERE id=? AND status='running' AND worker_id=?""",
                (json.dumps(result or {}, ensure_ascii=False), now, job_id, worker_id),
            )
            return cur.rowcount == 1

    def fail(self, job_id: str, worker_id: str, error: str, *, retry_delay: float = 1.0) -> bool:
        """Retry transient failures with bounded exponential backoff, or mark terminal."""
        now = time.time()
        with self._connect() as db:
            row = db.execute(
                "SELECT attempts,max_attempts FROM ingestion_jobs WHERE id=? AND status='running' AND worker_id=?",
                (job_id, worker_id),
            ).fetchone()
            if row is None:
                return False
            retry = row["attempts"] < row["max_attempts"]
            delay = min(300.0, max(0.0, retry_delay) * (2 ** max(0, row["attempts"] - 1)))
            db.execute(
                """UPDATE ingestion_jobs SET status=?, error=?, worker_id=NULL, lease_until=NULL,
                   available_at=?, updated_at=? WHERE id=?""",
                ("queued" if retry else "failed", str(error)[:2000], now + delay if retry else now, now, job_id),
            )
            return True

    def is_cancelled(self, job_id: str) -> bool:
        """Allow long-running processors to stop cleanly between batches."""
        with self._connect() as db:
            row = db.execute("SELECT status FROM ingestion_jobs WHERE id=?", (job_id,)).fetchone()
        return row is None or row["status"] == "cancelled"

    def cancel(self, job_id: str) -> bool:
        """Cancel queued or running work; workers check status between batches."""
        with self._connect() as db:
            cur = db.execute(
                """UPDATE ingestion_jobs SET status='cancelled', worker_id=NULL, lease_until=NULL,
                   updated_at=? WHERE id=? AND status IN ('queued','running')""",
                (time.time(), job_id),
            )
            return cur.rowcount == 1

    def process_one(self, processor: Callable[[IngestionJob, int], tuple[str | None, bool, dict[str, Any] | None]], *, batch_size: int = 32, worker_id: str | None = None) -> IngestionJob | None:
        """Run one bounded batch; processor returns (cursor, done, result).

        Processors must be idempotent for a repeated cursor. Persist side effects
        before returning a cursor so a crash can safely replay the current batch.
        """
        if batch_size < 1 or batch_size > 512:
            raise ValueError("batch_size must be between 1 and 512")
        worker = worker_id or str(uuid.uuid4())
        job = self.claim(worker_id=worker)
        if job is None:
            return None
        try:
            cursor, done, result = processor(job, batch_size)
            if done:
                self.complete(job.id, worker, result)
            else:
                self.checkpoint(job.id, worker, cursor)
        except Exception as exc:
            self.fail(job.id, worker, f"{type(exc).__name__}: {exc}")
        return self.get(job.id)

    def counts(self) -> dict[str, int]:
        with self._connect() as db:
            rows = db.execute("SELECT status, COUNT(*) AS total FROM ingestion_jobs GROUP BY status").fetchall()
        return {row["status"]: row["total"] for row in rows}
