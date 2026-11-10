from __future__ import annotations

import sqlite3
import time

import pytest

from app.services.ingestion_queue import IngestionQueue


def test_enqueue_is_idempotent_by_kind_and_content_hash(tmp_path):
    queue = IngestionQueue(tmp_path / "queue.sqlite3")
    first = queue.enqueue("document", {"name": "spec.md", "body": "hello"})
    duplicate = queue.enqueue("document", {"body": "hello", "name": "spec.md"})
    other_kind = queue.enqueue("attachment", {"name": "spec.md", "body": "hello"})

    assert duplicate.id == first.id
    assert other_kind.id != first.id
    assert queue.counts() == {"queued": 2}


def test_claim_checkpoint_and_resume_in_bounded_batches(tmp_path):
    queue = IngestionQueue(tmp_path / "queue.sqlite3")
    job = queue.enqueue("document", {"items": list(range(10))})
    observed = []

    def process_batch(claimed, batch_size):
        start = int(claimed.cursor or "0")
        batch = claimed.payload["items"][start : start + batch_size]
        observed.extend(batch)
        next_cursor = str(start + len(batch))
        return next_cursor, next_cursor == str(len(claimed.payload["items"])), {"processed": len(observed)}

    first = queue.process_one(process_batch, batch_size=3, worker_id="worker-a")
    assert first.status == "running"
    assert first.cursor == "3"
    assert observed == [0, 1, 2]

    second = queue.process_one(process_batch, batch_size=3, worker_id="worker-a")
    assert second.status == "running"
    assert second.cursor == "6"

    third = queue.process_one(process_batch, batch_size=8, worker_id="worker-a")
    assert third.status == "completed"
    assert third.result == {"processed": 10}
    assert observed == list(range(10))
    assert queue.get(job.id).status == "completed"


def test_expired_lease_is_recovered_and_old_worker_cannot_checkpoint(tmp_path):
    queue = IngestionQueue(tmp_path / "queue.sqlite3", lease_seconds=1)
    job = queue.enqueue("pdf", {"name": "report.pdf"})
    claimed = queue.claim(worker_id="worker-old")
    assert claimed and claimed.status == "running"

    with sqlite3.connect(queue.path) as db:
        db.execute("UPDATE ingestion_jobs SET lease_until=? WHERE id=?", (time.time() - 1, job.id))

    recovered = queue.claim(worker_id="worker-new")
    assert recovered and recovered.id == job.id
    assert recovered.attempts == 2
    assert queue.checkpoint(job.id, "worker-old", "stale") is False
    assert queue.checkpoint(job.id, "worker-new", "page:4") is True


def test_failures_retry_then_become_terminal(tmp_path):
    queue = IngestionQueue(tmp_path / "queue.sqlite3", max_attempts=2)
    job = queue.enqueue("image", {"name": "image.png"})
    first = queue.claim(worker_id="worker")
    assert first
    assert queue.fail(job.id, "worker", "temporary failure", retry_delay=0)

    second = queue.claim(worker_id="worker")
    assert second and second.attempts == 2
    assert queue.fail(job.id, "worker", "permanent failure", retry_delay=0)
    final = queue.get(job.id)
    assert final.status == "failed"
    assert final.error == "permanent failure"


def test_cancel_prevents_future_claims_and_completion(tmp_path):
    queue = IngestionQueue(tmp_path / "queue.sqlite3")
    job = queue.enqueue("video", {"name": "clip.mp4"})
    claimed = queue.claim(worker_id="worker")
    assert claimed
    assert queue.cancel(job.id) is True
    assert queue.is_cancelled(job.id) is True
    assert queue.complete(job.id, "worker", {"ok": True}) is False
    assert queue.claim(worker_id="another-worker") is None
    assert queue.get(job.id).status == "cancelled"
    assert queue.is_cancelled("missing-job") is True


def test_process_one_validates_batch_size(tmp_path):
    queue = IngestionQueue(tmp_path / "queue.sqlite3")
    with pytest.raises(ValueError):
        queue.process_one(lambda _job, _size: (None, True, None), batch_size=0)
