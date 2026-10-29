"""Explicitly started development previews for generated web applications.

Preview processes are separate from RunnerCore: they only manage a user-requested
local viewer process and never execute a project merely because files appeared.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from app.infra.workspace import RunWorkspace, safe_id


@dataclass
class PreviewProcess:
    execution_id: str
    package_path: str
    process: subprocess.Popen
    port: int
    log_path: Path
    started_at: float


class PreviewManager:
    STARTUP_TIMEOUT_SECONDS = 90
    MAX_LOG_CHARS = 8_000

    def __init__(self) -> None:
        self._processes: dict[str, PreviewProcess] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    @staticmethod
    def _environment(port: int) -> dict[str, str]:
        blocked = ("_API_KEY", "_TOKEN", "_SECRET", "PASSWORD", "PASSWD")
        env = {
            key: value for key, value in os.environ.items()
            if not any(marker in key.upper() for marker in blocked)
        }
        env.update({"PORT": str(port), "HOST": "127.0.0.1", "BROWSER": "none"})
        return env

    @classmethod
    def _log_tail(cls, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="replace")[-cls.MAX_LOG_CHARS:]
        except OSError:
            return ""

    @staticmethod
    def _is_listening(port: int) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return True
        except OSError:
            return False

    def _terminate(self, item: PreviewProcess) -> None:
        if item.process.poll() is not None:
            return
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(item.process.pid), "/T", "/F"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                item.process.kill()
        else:
            try:
                os.killpg(item.process.pid, 15)
                item.process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    os.killpg(item.process.pid, 9)
                except OSError:
                    pass
        try:
            item.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            item.process.kill()

    def start(self, execution_id: str, package_path: str) -> dict:
        safe_id(execution_id)
        workspace = RunWorkspace(execution_id)
        try:
            package_file = workspace.resolve(package_path)
        except (ValueError, OSError, RuntimeError) as exc:
            raise ValueError("Select a package.json inside this execution workspace.") from exc
        if package_file.name.casefold() != "package.json" or not package_file.is_file():
            raise ValueError("A valid package.json is required to start a preview.")

        try:
            package = json.loads(package_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("The app's package.json could not be read.") from exc
        scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
        if not isinstance(scripts, dict):
            scripts = {}
        script = "dev" if isinstance(scripts.get("dev"), str) else "start" if isinstance(scripts.get("start"), str) else None
        if not script:
            raise ValueError("Add a 'dev' or 'start' script to package.json before previewing this app.")

        npm = shutil.which("npm")
        if not npm:
            raise RuntimeError("Node.js and npm are required to run this app preview.")
        with self._lock:
            existing = self._processes.get(execution_id)
            if existing and existing.process.poll() is None:
                if existing.package_path == package_path:
                    return self.status(execution_id)
                self._terminate(existing)
                self._processes.pop(execution_id, None)

            port = self._port()
            log_path = workspace.resolve(".results/preview-server.log")
            log_path.parent.mkdir(parents=True, exist_ok=True)
            env = self._environment(port)
            command = [npm, "run", script]
            script_text = scripts.get(script, "")
            if "vite" in script_text.lower():
                command += ["--", "--host", "127.0.0.1", "--port", str(port), "--strictPort"]

            if os.name == "nt":
                command_text = subprocess.list2cmdline(command)
                launch = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", command_text]
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            else:
                launch = command
                creationflags = 0

            try:
                with log_path.open("ab") as log_file:
                    process = subprocess.Popen(
                        launch,
                        cwd=str(package_file.parent),
                        env=env,
                        stdin=subprocess.DEVNULL,
                        stdout=log_file,
                        stderr=subprocess.STDOUT,
                        creationflags=creationflags,
                        start_new_session=(os.name != "nt"),
                    )
            except OSError as exc:
                raise RuntimeError(f"Could not start the app preview: {exc}") from exc

            item = PreviewProcess(
                execution_id=execution_id,
                package_path=package_path,
                process=process,
                port=port,
                log_path=log_path,
                started_at=time.monotonic(),
            )
            self._processes[execution_id] = item
            return self._snapshot(item)

    def status(self, execution_id: str) -> dict:
        with self._lock:
            item = self._processes.get(execution_id)
            if item is None:
                return {"execution_id": execution_id, "status": "stopped", "url": None, "log": ""}
            if item.process.poll() is not None:
                self._processes.pop(execution_id, None)
                return self._snapshot(item, status="failed")
            if self._is_listening(item.port):
                return self._snapshot(item, status="ready")
            if time.monotonic() - item.started_at > self.STARTUP_TIMEOUT_SECONDS:
                self._terminate(item)
                self._processes.pop(execution_id, None)
                return self._snapshot(item, status="failed", error="Preview server did not become ready in time.")
            return self._snapshot(item, status="starting")

    def _snapshot(self, item: PreviewProcess, *, status: str | None = None, error: str | None = None) -> dict:
        resolved_status = status or ("failed" if item.process.poll() is not None else "starting")
        ready = resolved_status == "ready"
        return {
            "execution_id": item.execution_id,
            "status": resolved_status,
            "url": f"http://127.0.0.1:{item.port}" if ready else None,
            "package_path": item.package_path,
            "pid": item.process.pid,
            "log": self._log_tail(item.log_path),
            "error": error,
        }

    def stop(self, execution_id: str) -> dict:
        with self._lock:
            item = self._processes.pop(execution_id, None)
            if item is not None:
                self._terminate(item)
            return {"execution_id": execution_id, "status": "stopped", "url": None, "log": self._log_tail(item.log_path) if item else ""}

    def shutdown(self) -> None:
        with self._lock:
            items = list(self._processes.values())
            self._processes.clear()
        for item in items:
            self._terminate(item)


preview_manager = PreviewManager()
