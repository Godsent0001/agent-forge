"""Serialise read-modify-write of one task's state_json within this process.

Several writers rewrite the same JSON document (plan interpreter, integrity
audit, the agent's task-memory tool, execution results, conversation summary).
The interpreter now runs concurrently with the agent, so without this lock the
last writer would silently discard the other's changes.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from contextlib import contextmanager

_guard = threading.Lock()
_locks: defaultdict[str, threading.RLock] = defaultdict(threading.RLock)


@contextmanager
def task_state_lock(task_state_id: str | None):
    if not task_state_id:
        yield
        return
    with _guard:
        lock = _locks[task_state_id]
    with lock:
        yield
