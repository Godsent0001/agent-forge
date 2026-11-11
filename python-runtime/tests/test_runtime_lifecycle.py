from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

RUNTIME_ROOT = Path(__file__).resolve().parents[1]


def test_runtime_ready_auth_and_parent_watchdog(tmp_path):
    data_root = tmp_path / "user-data"
    env = os.environ.copy()
    env["AGENTFORGE_TOKEN"] = "runtime-lifecycle-test-token"
    env["AGENTFORGE_WATCH_PARENT"] = "1"
    env["AGENTFORGE_DATA_DIR"] = str(data_root)
    env["PORT"] = "0"
    env["AGENTFORGE_RUNNER"] = "fake"
    env.pop("AGENTFORGE_DEV", None)

    process = subprocess.Popen(
        [sys.executable, "-u", "main.py"],
        cwd=RUNTIME_ROOT,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    lines: queue.Queue[str | None] = queue.Queue()

    def read_output() -> None:
        try:
            assert process.stdout is not None
            for line in process.stdout:
                lines.put(line)
        finally:
            # Explicit EOF notification prevents the test from racing the
            # reader thread when the child exits immediately after shutdown.
            lines.put(None)

    reader = threading.Thread(target=read_output, name="runtime-test-stdout", daemon=True)
    reader.start()
    ready_port = None
    captured: list[str] = []
    deadline = time.monotonic() + 60
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            try:
                line = lines.get(timeout=min(0.2, max(0.01, deadline - time.monotonic())))
            except queue.Empty:
                continue
            if line is None:
                break
            captured.append(line)
            match = re.search(r"AGENTFORGE_READY:(\\d+)", line)
            if match:
                ready_port = int(match.group(1))
                break

        assert ready_port, "runtime never became ready; output:\\n" + "".join(captured[-40:])
        with urllib.request.urlopen(f"http://127.0.0.1:{ready_port}/health", timeout=3) as response:
            assert response.status == 200
            assert json.loads(response.read().decode("utf-8"))["status"] == "ok"

        try:
            urllib.request.urlopen(f"http://127.0.0.1:{ready_port}/settings/keys", timeout=3)
        except urllib.error.HTTPError as error:
            assert error.code == 401
        else:
            raise AssertionError("protected route unexpectedly accepted a request without a token")

        assert process.stdin is not None
        process.stdin.close()
        assert process.wait(timeout=10) == 0, "runtime did not exit after parent stdin closed"

        # Wait for the stdout reader's explicit EOF sentinel before draining;
        # joining for an arbitrary short interval can lose final lifespan logs.
        reader.join(timeout=5)
        assert not reader.is_alive(), "runtime stdout reader did not finish after child exit"
        while True:
            try:
                line = lines.get_nowait()
            except queue.Empty:
                break
            if line is None:
                continue
            captured.append(line)

        assert "AgentForge runtime shutdown complete." in "".join(captured), (
            "runtime exited without completing FastAPI lifespan cleanup; output:\\n"
            + "".join(captured[-40:])
        )
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        if process.stdout is not None:
            process.stdout.close()
        reader.join(timeout=1)
