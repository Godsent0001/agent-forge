"""Storage and validation boundary for uploaded project attachments (D-22)."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import stat
import unicodedata
from pathlib import Path, PurePosixPath
from urllib.parse import quote
from uuid import uuid4

from app.infra.paths import data_dir

MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024
MAX_PROJECT_UPLOAD_BYTES = 500 * 1024 * 1024
MAX_RUN_ATTACHMENTS = 20
MAX_RUN_ATTACHMENT_BYTES = 100 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
ALLOWED_MIME_BY_EXTENSION: dict[str, str] = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".json": "application/json",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
}
_KEY_RE = re.compile(r"^[0-9a-f]{64}$")
ACTIVE_TEXT_RE = re.compile(
    r"(?:<!doctype\s+html|<html\b|<script\b|<svg\b|<iframe\b|<object\b|<embed\b|javascript:)",
    re.IGNORECASE,
)


class AttachmentStorageError(ValueError):
    """A storage root/key is unsafe or a stored blob is not a regular file."""


def upload_dirs() -> tuple[Path, Path, Path]:
    root = (data_dir() / "uploads").resolve()
    quarantine = root / "quarantine"
    objects = root / "objects"
    root.mkdir(parents=True, exist_ok=True)
    for directory in (quarantine, objects):
        if directory.is_symlink():
            raise AttachmentStorageError("Upload storage directories must not be symlinks")
        directory.mkdir(parents=True, exist_ok=True)
        if not directory.resolve().is_relative_to(root):
            raise AttachmentStorageError("Upload storage directory escaped its root")
    return root, quarantine, objects


def cleanup_stale_upload_parts() -> int:
    """Remove interrupted staging files before the runtime accepts requests."""
    _, quarantine, _ = upload_dirs()
    deleted = 0
    for candidate in quarantine.glob("*.part"):
        try:
            if candidate.is_symlink() or not stat.S_ISREG(candidate.lstat().st_mode):
                continue
            candidate.unlink()
            deleted += 1
        except FileNotFoundError:
            continue
    return deleted


def new_storage_key() -> str:
    return os.urandom(32).hex()


def safe_original_name(value: str | None) -> str:
    raw = (value or "upload").replace("\\", "/").split("/")[-1].strip()
    raw = "".join(ch for ch in raw if unicodedata.category(ch) not in {"Cc", "Cf"} and ch not in {"/", "\\\\"})
    raw = raw.strip(" .") or "upload"
    encoded = raw.encode("utf-8")[:255]
    while encoded:
        try:
            return encoded.decode("utf-8")
        except UnicodeDecodeError:
            encoded = encoded[:-1]
    return "upload"


def resolve_blob(storage_key: str, *, clean: bool) -> Path:
    if not isinstance(storage_key, str) or not _KEY_RE.fullmatch(storage_key):
        raise AttachmentStorageError("Invalid attachment storage key")
    root, quarantine, objects = upload_dirs()
    directory = objects if clean else quarantine
    path = directory / f"{storage_key}.blob"
    if path.is_symlink():
        raise AttachmentStorageError("Stored attachment must not be a symlink")
    resolved = path.resolve()
    if not resolved.is_relative_to(root) or not resolved.is_relative_to(directory.resolve()):
        raise AttachmentStorageError("Stored attachment escaped its storage root")
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        raise
    if not stat.S_ISREG(mode):
        raise AttachmentStorageError("Stored attachment is not a regular file")
    return resolved


def remove_attachment_blobs(storage_key: str) -> None:
    _, quarantine, objects = upload_dirs()
    if not _KEY_RE.fullmatch(storage_key or ""):
        raise AttachmentStorageError("Invalid attachment storage key")
    # A partial object can exist if the process stopped while copying/promoting.
    for directory, suffix in ((quarantine, ".blob"), (objects, ".blob"), (quarantine, ".part")):
        candidate = directory / f"{storage_key}{suffix}"
        if candidate.is_symlink():
            raise AttachmentStorageError("Refusing to remove a symlink from upload storage")
        try:
            mode = candidate.lstat().st_mode
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(mode):
            raise AttachmentStorageError("Refusing to remove a non-regular upload object")
        resolved = candidate.resolve()
        if not resolved.is_relative_to(directory.resolve()):
            raise AttachmentStorageError("Upload object escaped its storage root")
        candidate.unlink()


def _assert_safe_text(data: bytes, extension: str) -> str:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AttachmentStorageError("Text files must be valid UTF-8") from exc
    if "\x00" in text:
        raise AttachmentStorageError("Binary data is not allowed in text attachments")
    if any(unicodedata.category(ch) == "Cc" and ch not in "\t\n\r\f" for ch in text):
        raise AttachmentStorageError("Text contains unsupported control characters")
    if ACTIVE_TEXT_RE.search(text[:8192]):
        raise AttachmentStorageError("HTML, SVG, scripts, and active text documents are not allowed")
    if extension == ".json":
        try:
            json.loads(text)
        except (json.JSONDecodeError, RecursionError) as exc:
            raise AttachmentStorageError("Malformed JSON file") from exc
    return text


def validate_attachment(path: Path, original_name: str, declared_mime: str | None) -> str:
    extension = Path(original_name).suffix.lower()
    expected_mime = ALLOWED_MIME_BY_EXTENSION.get(extension)
    if expected_mime is None:
        raise AttachmentStorageError("Unsupported file type")
    try:
        size = path.stat().st_size
        if size <= 0:
            raise AttachmentStorageError("Empty files are not allowed")
        if size > MAX_ATTACHMENT_BYTES:
            raise AttachmentStorageError("Attachment exceeds the 25 MiB file limit")
        with path.open("rb") as handle:
            head = handle.read(64)
            handle.seek(max(0, size - 2048))
            tail = handle.read(2048)
            handle.seek(0)
            data = handle.read(MAX_ATTACHMENT_BYTES + 1)
    except OSError as exc:
        raise AttachmentStorageError("Uploaded file could not be read") from exc
    if len(data) != size:
        raise AttachmentStorageError("Uploaded file was truncated while validating")

    if extension in {".txt", ".md", ".csv", ".json"}:
        _assert_safe_text(data, extension)
        mime = expected_mime
    elif extension == ".pdf":
        if not head.startswith(b"%PDF-") or b"%%EOF" not in tail:
            raise AttachmentStorageError("Malformed PDF or extension/signature mismatch")
        mime = "application/pdf"
    elif extension == ".png":
        if not head.startswith(bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])):
            raise AttachmentStorageError("PNG signature mismatch")
        _verify_image(path, "PNG")
        mime = "image/png"
    elif extension in {".jpg", ".jpeg"}:
        if not head.startswith(bytes([0xFF, 0xD8, 0xFF])):
            raise AttachmentStorageError("JPEG signature mismatch")
        _verify_image(path, "JPEG")
        mime = "image/jpeg"
    elif extension == ".webp":
        if head[:4] != b"RIFF" or head[8:12] != b"WEBP":
            raise AttachmentStorageError("WebP signature mismatch")
        _verify_image(path, "WEBP")
        mime = "image/webp"
    elif extension == ".wav":
        if head[:4] != b"RIFF" or head[8:12] != b"WAVE":
            raise AttachmentStorageError("WAV signature mismatch")
        mime = "audio/wav"
    elif extension == ".mp3":
        if not (head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0)):
            raise AttachmentStorageError("MP3 signature mismatch")
        mime = "audio/mpeg"
    elif extension == ".mp4":
        if len(head) < 12 or head[4:8] != b"ftyp":
            raise AttachmentStorageError("MP4 signature mismatch")
        mime = "video/mp4"
    elif extension == ".webm":
        if not head.startswith(bytes([0x1A, 0x45, 0xDF, 0xA3])):
            raise AttachmentStorageError("WebM signature mismatch")
        mime = "video/webm"
    else:
        raise AttachmentStorageError("Unsupported file type")

    claimed = (declared_mime or "").split(";", 1)[0].strip().lower()
    mime_aliases = {
        "text/x-markdown": "text/markdown",
        "application/x-pdf": "application/pdf",
        "image/jpg": "image/jpeg",
        "audio/x-wav": "audio/wav",
        "audio/wave": "audio/wav",
        "application/octet-stream": "",
        "binary/octet-stream": "",
    }
    claimed = mime_aliases.get(claimed, claimed)
    if claimed and claimed != mime:
        raise AttachmentStorageError("Declared MIME type does not match the detected file type")
    if expected_mime != mime:
        raise AttachmentStorageError("File extension and detected MIME type do not match")
    return mime


def _verify_image(path: Path, expected_format: str) -> None:
    try:
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = 40_000_000
        with Image.open(path) as image:
            if image.format != expected_format:
                raise AttachmentStorageError("Image extension and detected format do not match")
            image.verify()
    except AttachmentStorageError:
        raise
    except Exception as exc:  # Pillow can raise format/decompression exceptions.
        raise AttachmentStorageError("Image is malformed or exceeds safe decoder limits") from exc


def _find_windows_defender_scanner() -> str | None:
    """Locate Microsoft's installed scanner without assuming a versioned path."""
    program_data = Path(os.environ.get("PROGRAMDATA", r"C:\\ProgramData"))
    program_files = Path(os.environ.get("PROGRAMFILES", r"C:\\Program Files"))
    candidates: list[Path] = []
    platform_dir = program_data / "Microsoft" / "Windows Defender" / "Platform"
    try:
        candidates.extend(
            folder / "MpCmdRun.exe"
            for folder in sorted(platform_dir.iterdir(), reverse=True)
            if folder.is_dir()
        )
    except OSError:
        pass
    candidates.append(program_files / "Windows Defender" / "MpCmdRun.exe")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


async def _scan_with_windows_defender(path: Path, executable: str) -> tuple[str, str | None]:
    """Run a non-remediating custom scan; any ambiguous result remains quarantined."""
    try:
        proc = await asyncio.create_subprocess_exec(
            executable,
            "-Scan", "-ScanType", "3", "-File", str(path), "-DisableRemediation",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return "error", "Microsoft Defender Antivirus"
        # MpCmdRun documents 0 as no malware found (or successful remediation) and
        # 2 as malware not remediated or a scan error. DisableRemediation prevents
        # the scanner from modifying the quarantined upload, so only 0 is clean.
        _ = (stdout, stderr)
        if proc.returncode == 0:
            return "clean", "Microsoft Defender Antivirus"
        return "error", "Microsoft Defender Antivirus"
    except OSError:
        return "error", "Microsoft Defender Antivirus"


async def scan_attachment(path: Path) -> tuple[str, str | None]:
    """Return clean/infected/unavailable/error. Missing or failed scanner fails closed."""
    scanner = os.environ.get("AGENTFORGE_AV_SCANNER", "clamscan")
    executable = shutil.which(scanner) or (scanner if Path(scanner).is_absolute() and Path(scanner).is_file() else None)
    if not executable:
        # Windows desktop installs normally have Microsoft Defender but do not have
        # ClamAV. Prefer the OS scanner rather than requiring a separate AV install.
        if scanner == "clamscan" and os.name == "nt":
            defender = _find_windows_defender_scanner()
            if defender:
                return await _scan_with_windows_defender(path, defender)
        return "unavailable", None
    try:
        version_proc = await asyncio.create_subprocess_exec(
            executable, "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        version_out, _ = await asyncio.wait_for(version_proc.communicate(), timeout=3)
        version = version_out.decode("utf-8", errors="replace").strip()[:128] if version_proc.returncode == 0 else None
        proc = await asyncio.create_subprocess_exec(
            executable, "--no-summary", "--infected", str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return "error", version
        if proc.returncode == 0:
            return "clean", version
        if proc.returncode == 1:
            return "infected", version
        # Do not leak scanner output into API errors or logs: it can contain paths.
        _ = (stdout, stderr)
        return "error", version
    except (OSError, asyncio.TimeoutError):
        return "error", None


async def stream_to_staging(upload, *, storage_key: str, used_project_bytes: int) -> tuple[Path, int, str]:
    _, quarantine, _ = upload_dirs()
    staging = quarantine / f"{storage_key}.part"
    if staging.is_symlink() or staging.exists():
        raise AttachmentStorageError("Staging key collision")
    digest = hashlib.sha256()
    total = 0
    try:
        with staging.open("xb") as output:
            while True:
                chunk = await upload.read(CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_ATTACHMENT_BYTES:
                    raise OverflowError("Attachment exceeds the 25 MiB file limit")
                if used_project_bytes + total > MAX_PROJECT_UPLOAD_BYTES:
                    raise OverflowError("Project has reached its 500 MiB upload quota")
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if total == 0:
            raise AttachmentStorageError("Empty files are not allowed")
        return staging, total, digest.hexdigest()
    except BaseException:
        try:
            if staging.is_file() and not staging.is_symlink():
                staging.unlink()
        except OSError:
            pass
        raise


def promote_staged_file(staging: Path, storage_key: str, *, clean: bool) -> Path:
    _, quarantine, objects = upload_dirs()
    if staging.is_symlink() or not staging.is_file():
        raise AttachmentStorageError("Staging file is not a regular file")
    dest_dir = objects if clean else quarantine
    dest = dest_dir / f"{storage_key}.blob"
    if dest.exists() or dest.is_symlink():
        raise AttachmentStorageError("Storage key already exists")
    if not staging.resolve().is_relative_to(quarantine.resolve()) or not dest_dir.resolve().is_relative_to(quarantine.parent.resolve()):
        raise AttachmentStorageError("Attachment promotion escaped storage root")
    os.replace(staging, dest)
    return resolve_blob(storage_key, clean=clean)


def promote_quarantined_blob_to_clean(storage_key: str) -> Path:
    """Atomically promote a previously quarantined object after a clean rescan."""
    _, quarantine, objects = upload_dirs()
    source = resolve_blob(storage_key, clean=False)
    destination = objects / f"{storage_key}.blob"
    if destination.exists() or destination.is_symlink():
        raise AttachmentStorageError("Clean storage key already exists")
    if not source.resolve().is_relative_to(quarantine.resolve()):
        raise AttachmentStorageError("Quarantined attachment escaped its storage root")
    os.replace(source, destination)
    return resolve_blob(storage_key, clean=True)


def content_disposition(filename: str) -> str:
    safe = safe_original_name(filename)
    fallback = re.sub(r"[^A-Za-z0-9._-]", "_", safe) or "attachment"
    return f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{quote(safe, safe="")}'


def copy_clean_attachment_to_workspace(attachment, workspace) -> str:
    """Verify blob integrity and copy it to a new, run-private workspace-relative path."""
    source = resolve_blob(attachment.storage_key, clean=True)
    if source.stat().st_size != attachment.size_bytes:
        raise AttachmentStorageError("Stored attachment size changed after scanning")
    extension = PurePosixPath(attachment.original_name.replace("\\\\", "/")).suffix.lower()
    if extension not in ALLOWED_MIME_BY_EXTENSION:
        raise AttachmentStorageError("Stored attachment has an unsupported extension")
    destination = workspace.new_path(f"attachments/{uuid4().hex}{extension}")
    digest = hashlib.sha256()
    total = 0
    try:
        with source.open("rb") as incoming, destination.open("xb") as outgoing:
            while True:
                chunk = incoming.read(CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                digest.update(chunk)
                outgoing.write(chunk)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        if total != attachment.size_bytes or digest.hexdigest() != attachment.sha256:
            raise AttachmentStorageError("Stored attachment failed integrity verification")
        return workspace.relative(destination)
    except BaseException:
        try:
            if destination.is_file() and not destination.is_symlink():
                destination.unlink()
        except OSError:
            pass
        raise
