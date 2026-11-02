"""Project-scoped persistent local terminal sessions for long-running commands."""
from __future__ import annotations

import asyncio
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from app.tools.shell import _terminate_process_tree

_MAX_BUFFER_CHARS = 120_000


@dataclass
class ShellSession:
    session_id: str
    project_id: str
    cwd: Path
    process: asyncio.subprocess.Process
    output: str = ""
    reader_task: asyncio.Task | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def capture(self) -> None:
        assert self.process.stdout is not None
        while True:
            chunk = await self.process.stdout.read(4096)
            if not chunk:
                return
            text = chunk.decode("utf-8", errors="replace")
            async with self.lock:
                self.output = (self.output + text)[-_MAX_BUFFER_CHARS:]

    async def read(self, max_chars: int = 12_000) -> str:
        async with self.lock:
            if not self.output:
                status = "running" if self.process.returncode is None else f"exited ({self.process.returncode})"
                return f"No new terminal output. Session {status}."
            result = self.output[:max_chars]
            self.output = self.output[len(result):]
            if len(result) == max_chars and self.output:
                result += "\n[More output is available; call read again.]"
            return result

    async def write(self, text: str) -> None:
        if self.process.returncode is not None or self.process.stdin is None:
            raise RuntimeError("Terminal session has already exited.")
        self.process.stdin.write(text.encode("utf-8") + b"\n")
        await self.process.stdin.drain()

    async def stop(self) -> None:
        if self.process.returncode is None:
            await _terminate_process_tree(self.process)
        if self.reader_task and not self.reader_task.done():
            self.reader_task.cancel()
            await asyncio.gather(self.reader_task, return_exceptions=True)


class ShellSessionManager:
    """Keeps long-running CMD/shell processes addressable across agent turns."""

    def __init__(self) -> None:
        self._sessions: dict[str, ShellSession] = {}
        self._lock = asyncio.Lock()

    async def start(self, *, project_id: str, cwd: Path, command: str) -> ShellSession:
        if os.name == "nt":
            shell = os.environ.get("COMSPEC", "cmd.exe")
            argv = [shell, "/d", "/q"]
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        else:
            argv = ["/bin/sh"]
            creationflags = 0
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(cwd),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=os.environ.copy(),
            creationflags=creationflags,
            start_new_session=(os.name != "nt"),
        )
        session = ShellSession(str(uuid4()), project_id, cwd, process)
        session.reader_task = asyncio.create_task(session.capture())
        async with self._lock:
            self._sessions[session.session_id] = session
        try:
            await session.write(command)
        except Exception:
            await session.stop()
            async with self._lock:
                self._sessions.pop(session.session_id, None)
            raise
        return session

    async def get(self, session_id: str, project_id: str) -> ShellSession:
        async with self._lock:
            session = self._sessions.get(session_id)
        if session is None or session.project_id != project_id:
            raise ValueError("Terminal session was not found in this project.")
        return session

    async def stop(self, session_id: str, project_id: str) -> bool:
        session = await self.get(session_id, project_id)
        await session.stop()
        async with self._lock:
            self._sessions.pop(session_id, None)
        return True

    async def stop_all(self) -> None:
        async with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        if sessions:
            await asyncio.gather(*(session.stop() for session in sessions), return_exceptions=True)


shell_sessions = ShellSessionManager()
