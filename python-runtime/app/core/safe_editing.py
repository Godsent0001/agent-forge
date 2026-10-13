"""Safe, versioned workspace editing with optimistic concurrency and rollback.

This layer is intentionally format-neutral. Domain editors (image/video/code/document)
can produce transformed bytes, then use the same guarded apply/backup contract.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


class EditError(RuntimeError):
    pass


class EditConflict(EditError):
    """The target changed since the edit was prepared."""


class EditValidationError(EditError):
    pass


@dataclass(frozen=True)
class TextReplacement:
    expected_text: str
    replacement_text: str
    expected_count: int = 1


@dataclass(frozen=True)
class EditPreview:
    path: str
    original_sha256: str
    proposed_sha256: str
    unified_diff: str
    changed: bool
    original_bytes: int
    proposed_bytes: int


@dataclass(frozen=True)
class AppliedEdit:
    edit_id: str
    path: str
    backup_path: str
    original_sha256: str
    new_sha256: str
    changed_at: str


class SafeWorkspaceEditor:
    """Edits only files under root; verifies base hash and writes atomically."""

    def __init__(self, root: str | Path, *, max_file_bytes: int = 100 * 1024 * 1024):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.state = self.root / ".agentforge" / "edits"
        self.backups = self.state / "backups"
        self.backups.mkdir(parents=True, exist_ok=True)
        self.manifest = self.state / "history.jsonl"
        self.max_file_bytes = max_file_bytes

    def _resolve(self, relative_path: str) -> Path:
        candidate = Path(relative_path)
        if candidate.is_absolute():
            raise EditValidationError("Absolute paths are not allowed.")
        resolved = (self.root / candidate).resolve()
        if resolved == self.root or self.root not in resolved.parents:
            raise EditValidationError("Edit path escapes the workspace.")
        # Disallow editing internal AgentForge state directly.
        if self.root / ".agentforge" in resolved.parents or resolved == self.root / ".agentforge":
            raise EditValidationError("AgentForge internal state is not an editable target.")
        return resolved

    def read(self, relative_path: str) -> tuple[bytes, str]:
        path = self._resolve(relative_path)
        if not path.is_file():
            raise FileNotFoundError(relative_path)
        data = path.read_bytes()
        if len(data) > self.max_file_bytes:
            raise EditValidationError("Target exceeds configured edit size limit.")
        return data, hashlib.sha256(data).hexdigest()

    def preview_bytes(self, relative_path: str, proposed: bytes, *, expected_sha256: str | None = None) -> EditPreview:
        original, digest = self.read(relative_path)
        if expected_sha256 and digest != expected_sha256:
            raise EditConflict("Target hash changed; re-read and regenerate the edit.")
        if not isinstance(proposed, bytes):
            raise TypeError("proposed must be bytes")
        if len(proposed) > self.max_file_bytes:
            raise EditValidationError("Proposed content exceeds configured edit size limit.")
        try:
            old_text = original.decode("utf-8")
            new_text = proposed.decode("utf-8")
        except UnicodeDecodeError:
            old_text = new_text = ""
            diff = "[binary edit: byte-level diff unavailable]"
        else:
            diff = "".join(difflib.unified_diff(
                old_text.splitlines(keepends=True), new_text.splitlines(keepends=True),
                fromfile=f"a/{relative_path}", tofile=f"b/{relative_path}",
            ))
        return EditPreview(
            path=relative_path, original_sha256=digest,
            proposed_sha256=hashlib.sha256(proposed).hexdigest(), unified_diff=diff,
            changed=original != proposed, original_bytes=len(original), proposed_bytes=len(proposed),
        )

    def preview_replacements(
        self, relative_path: str, replacements: Iterable[TextReplacement], *, expected_sha256: str | None = None,
    ) -> tuple[EditPreview, bytes]:
        original, digest = self.read(relative_path)
        if expected_sha256 and digest != expected_sha256:
            raise EditConflict("Target hash changed; re-read and regenerate the edit.")
        try:
            text = original.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EditValidationError("Text replacements require a UTF-8 text file.") from exc
        updated = text
        for item in replacements:
            if not item.expected_text:
                raise EditValidationError("expected_text must not be empty.")
            count = updated.count(item.expected_text)
            if count != item.expected_count:
                raise EditConflict(
                    f"Expected {item.expected_count} occurrence(s) of target text, found {count}; nothing was changed."
                )
            updated = updated.replace(item.expected_text, item.replacement_text)
        proposed = updated.encode("utf-8")
        return self.preview_bytes(relative_path, proposed, expected_sha256=digest), proposed

    def apply(
        self, relative_path: str, proposed: bytes, *, expected_sha256: str,
        actor: str = "agent", reason: str = "workspace edit",
    ) -> AppliedEdit:
        path = self._resolve(relative_path)
        original, current_hash = self.read(relative_path)
        if current_hash != expected_sha256:
            raise EditConflict("Target changed after preview; nothing was written.")
        preview = self.preview_bytes(relative_path, proposed, expected_sha256=expected_sha256)
        if not preview.changed:
            raise EditValidationError("Proposed content is identical to the current file.")
        edit_id = str(uuid.uuid4())
        backup = self.backups / f"{edit_id}.bak"
        self._atomic_write(backup, original)
        self._atomic_write(path, proposed)
        now = datetime.now(timezone.utc).isoformat()
        record = {
            "edit_id": edit_id, "path": relative_path, "backup_path": str(backup.relative_to(self.root)),
            "original_sha256": current_hash, "new_sha256": preview.proposed_sha256,
            "actor": actor[:200], "reason": reason[:2000], "changed_at": now,
        }
        with self.manifest.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return AppliedEdit(edit_id, relative_path, record["backup_path"], current_hash, preview.proposed_sha256, now)

    def apply_replacements(
        self, relative_path: str, replacements: Iterable[TextReplacement], *,
        expected_sha256: str, actor: str = "agent", reason: str = "targeted text replacement",
    ) -> AppliedEdit:
        _, proposed = self.preview_replacements(relative_path, replacements, expected_sha256=expected_sha256)
        return self.apply(relative_path, proposed, expected_sha256=expected_sha256, actor=actor, reason=reason)

    def rollback(self, edit_id: str, *, expected_current_sha256: str) -> AppliedEdit:
        record = next((r for r in self.history() if r["edit_id"] == edit_id), None)
        if record is None:
            raise EditValidationError(f"Unknown edit id: {edit_id}")
        backup = (self.root / record["backup_path"]).resolve()
        if self.root not in backup.parents or not backup.is_file():
            raise EditValidationError("Backup is missing or outside the workspace.")
        original_content = backup.read_bytes()
        return self.apply(
            record["path"], original_content, expected_sha256=expected_current_sha256,
            actor="rollback", reason=f"Rollback edit {edit_id}",
        )

    def history(self) -> list[dict]:
        if not self.manifest.exists():
            return []
        result = []
        for line in self.manifest.read_text(encoding="utf-8").splitlines():
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                # Ignore a final partial line after a process interruption.
                continue
        return result

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".agentforge-write-", dir=str(path.parent))
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
