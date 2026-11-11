"""Project-scoped persistent local terminal sessions for long-running commands."""
from __future__ import annotations

import asyncio
import os
import subprocess
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from app.tools.shell import _safe_environment, _terminate_process_tree

_MAX_BUFFER_CHARS = 120_000
_MAX_SESSIONS = 4


@dataclass
class ShellSession:
    session_id: str
    project_id: str
    cwd: Path
    process: asyncio.subprocess.Process
    output_chunks: deque[str] = field(default_factory=deque)
    output_chars: int = 0
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
                self.output_chunks.append(text)
                self.output_chars += len(text)
                excess = self.output_chars - _MAX_BUFFER_CHARS
                while excess > 0 and self.output_chunks:
                    first = self.output_chunks[0]
                    if len(first) <= excess:
                        self.output_chunks.popleft()
                        self.output_chars -= len(first)
                        excess -= len(first)
                    else:
                        self.output_chunks[0] = first[excess:]
                        self.output_chars -= excess
                        excess = 0

    async def read(self, max_chars: int = 12_000) -> str:
        async with self.lock:
            if not self.output_chunks:
                status = "running" if self.process.returncode is None else f"exited ({self.process.returncode})"
                return f"No new terminal output. Session {status}."
            parts: list[str] = []
            remaining = max_chars
            while remaining > 0 and self.output_chunks:
                chunk = self.output_chunks[0]
                if len(chunk) <= remaining:
                    parts.append(self.output_chunks.popleft())
                    self.output_chars -= len(chunk)
                    remaining -= len(chunk)
                else:
                    parts.append(chunk[:remaining])
                    self.output_chunks[0] = chunk[remaining:]
                    self.output_chars -= remaining
                    remaining = 0
            result = "".join(parts)
            if self.output_chunks:
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
        # Serialize capacity checks with process creation so concurrent requests
        # cannot exceed the per-runtime persistent terminal limit.
        async with self._lock:
            for session_id, existing in tuple(self._sessions.items()):
                if existing.process.returncode is not None:
                    self._sessions.pop(session_id, None)
            if len(self._sessions) >= _MAX_SESSIONS:
                raise RuntimeError(
                    f"AgentForge allows at most {_MAX_SESSIONS} persistent terminal sessions. "
                    "Stop an existing session before starting another."
                )

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
                env=_safe_environment(cwd),
                creationflags=creationflags,
                start_new_session=(os.name != "nt"),
            )
            session = ShellSession(str(uuid4()), project_id, cwd, process)
            session.reader_task = asyncio.create_task(session.capture())
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
