"""Transcript-first video clip pipeline.

Finding the right part of a long video by having a multimodal model "watch"
it costs on the order of a million tokens per hour of footage. Almost every
clip request is really about what is *said* (a topic, a quote, a moment in a
discussion), so this module works from timestamped text instead:

1. ``video_transcript`` gets timestamped text for a URL or workspace file.
   It prefers captions published with the video (free, no media download),
   then YouTube-style auto captions, and only then falls back to local
   speech-to-text (faster-whisper, optional) on an audio-only download.
2. ``clip_finder`` ranks transcript windows against a query locally (BM25
   plus phrase and chapter boosts) and returns a handful of candidate clips
   with short excerpts. No model tokens are spent on the search itself; the
   agent only reads the shortlist.
3. ``clip_extractor`` downloads only the chosen sections with yt-dlp
   (``download_ranges``) or cuts a local file with ffmpeg.

An hour of speech is roughly 9-10k words, so even reading the full outline
is ~12k tokens; a typical find-and-cut round trip is a few thousand.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import shutil
import tempfile
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from pydantic import BaseModel, Field, field_validator

from app.contracts.tools import ArtifactRef, Tool, ToolContext, ToolError, ToolResult
from app.infra.paths import data_dir
from app.tools.base import ToolExecutionError
from app.tools.media_codecs import bitrate_for_height, h264_args
from app.tools.video_source import guard_media_url

# Hard limits keep one tool call from turning into an unbounded download.
MAX_CLIPS_PER_CALL = 20
MAX_CLIP_SECONDS = 600.0
MAX_TOTAL_CLIP_SECONDS = 1800.0
MAX_WHISPER_SOURCE_SECONDS = 4 * 3600
DEFAULT_OUTLINE_CHARS = 5500  # stays under the runner's 6000-char tool-result head
TRANSCRIPT_CACHE_VERSION = 1

_SUB_EXT_PREFERENCE = ("json3", "vtt", "srv3", "srt")
_LOCAL_MEDIA_SUFFIXES = {
    ".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi", ".mp3", ".m4a", ".wav",
    ".ogg", ".opus", ".flac", ".aac",
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class Chapter:
    title: str
    start: float
    end: float | None = None


@dataclass
class Transcript:
    source: str
    title: str = ""
    duration: float | None = None
    language: str | None = None
    origin: str = "unknown"  # manual_captions | auto_captions | whisper | file
    webpage_url: str | None = None
    chapters: list[Chapter] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["version"] = TRANSCRIPT_CACHE_VERSION
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Transcript:
        return cls(
            source=str(data.get("source", "")),
            title=str(data.get("title") or ""),
            duration=_float_or_none(data.get("duration")),
            language=data.get("language"),
            origin=str(data.get("origin") or "unknown"),
            webpage_url=data.get("webpage_url"),
            chapters=[
                Chapter(str(c.get("title") or ""), float(c.get("start") or 0.0), _float_or_none(c.get("end")))
                for c in data.get("chapters") or []
            ],
            segments=[
                Segment(float(s["start"]), float(s["end"]), str(s["text"]))
                for s in data.get("segments") or []
                if s.get("text")
            ],
        )

    @property
    def end_time(self) -> float:
        if self.duration:
            return float(self.duration)
        return self.segments[-1].end if self.segments else 0.0


def _float_or_none(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

_TS_RE = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{1,2}(?:[.,]\d+)?)$")


def parse_timestamp(value: float | int | str) -> float:
    """Accept seconds (``95``/``"95.5"``) or clock time (``"1:35"``, ``"01:02:03.5"``)."""
    if isinstance(value, bool):
        raise ValueError("timestamp must be a number or H:MM:SS string")
    if isinstance(value, (int, float)):
        seconds = float(value)
    else:
        raw = str(value).strip()
        match = _TS_RE.match(raw)
        if match:
            hours, minutes, secs = match.groups()
            seconds = int(hours or 0) * 3600 + int(minutes) * 60 + float(secs.replace(",", "."))
        else:
            try:
                seconds = float(raw)
            except ValueError as exc:
                raise ValueError(f"invalid timestamp: {value!r}") from exc
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError(f"invalid timestamp: {value!r}")
    return seconds


def format_timestamp(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _srt_time(seconds: float) -> str:
    ms = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


# ---------------------------------------------------------------------------
# Caption parsers
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_CUE_TIME_RE = re.compile(
    r"((?:\d+:)?\d{1,2}:\d{2}[.,]\d{1,3})\s*-->\s*((?:\d+:)?\d{1,2}:\d{2}[.,]\d{1,3})"
)
_SPACE_RE = re.compile(r"\s+")


def _clean_caption_text(text: str) -> str:
    import html

    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    return _SPACE_RE.sub(" ", text).strip()


def parse_json3(raw: str) -> list[Segment]:
    """YouTube's json3 caption format (works for both manual and auto captions)."""
    data = json.loads(raw)
    segments: list[Segment] = []
    for event in data.get("events") or []:
        segs = event.get("segs")
        if not segs:
            continue
        text = _clean_caption_text("".join(str(s.get("utf8", "")) for s in segs))
        if not text:
            continue
        start = float(event.get("tStartMs", 0)) / 1000.0
        end = start + float(event.get("dDurationMs", 0)) / 1000.0
        segments.append(Segment(start, max(end, start), text))
    return _normalize_segments(segments)


def parse_cues(raw: str) -> list[Segment]:
    """WebVTT or SRT. Collapses the rolling duplicate lines auto captions emit."""
    segments: list[Segment] = []
    recent: list[str] = []
    blocks = re.split(r"\r?\n\s*\r?\n", raw.replace("﻿", ""))
    for block in blocks:
        lines = [line for line in block.splitlines() if line.strip()]
        for idx, line in enumerate(lines):
            match = _CUE_TIME_RE.search(line)
            if not match:
                continue
            start = parse_timestamp(match.group(1))
            end = parse_timestamp(match.group(2))
            new_lines = []
            for text_line in lines[idx + 1:]:
                cleaned = _clean_caption_text(text_line)
                if not cleaned or cleaned in recent:
                    continue
                new_lines.append(cleaned)
                recent = (recent + [cleaned])[-3:]
            if new_lines:
                segments.append(Segment(start, max(end, start), " ".join(new_lines)))
            break
    return _normalize_segments(segments)


def parse_captions(raw: str, ext: str) -> list[Segment]:
    ext = ext.lower().lstrip(".")
    if ext == "json3":
        return parse_json3(raw)
    if ext == "srv3":
        return _parse_srv3(raw)
    return parse_cues(raw)


def _parse_srv3(raw: str) -> list[Segment]:
    import xml.etree.ElementTree as ET

    root = ET.fromstring(raw)
    segments: list[Segment] = []
    for node in root.iter("p"):
        text = _clean_caption_text("".join(node.itertext()))
        if not text:
            continue
        start = float(node.get("t", 0)) / 1000.0
        end = start + float(node.get("d", 0)) / 1000.0
        segments.append(Segment(start, end, text))
    return _normalize_segments(segments)


def _normalize_segments(segments: list[Segment]) -> list[Segment]:
    """Sort, drop exact repeats, and make sure every segment ends after it starts."""
    segments = sorted(segments, key=lambda s: (s.start, s.end))
    out: list[Segment] = []
    for seg in segments:
        if out and seg.text == out[-1].text and seg.start - out[-1].end < 1.0:
            out[-1].end = max(out[-1].end, seg.end)
            continue
        out.append(Segment(seg.start, seg.end, seg.text))
    for idx, seg in enumerate(out):
        if seg.end <= seg.start:
            nxt = out[idx + 1].start if idx + 1 < len(out) else seg.start + 2.0
            seg.end = max(seg.start + 0.5, nxt)
    return out


# ---------------------------------------------------------------------------
# Transcript acquisition
# ---------------------------------------------------------------------------


def _is_url(source: str) -> bool:
    return urlparse(source).scheme.lower() in {"http", "https"}


def _ydl_base_opts(config: dict[str, Any]) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "retries": 3,
    }
    browser = config.get("cookies_from_browser")
    if isinstance(browser, str) and re.fullmatch(r"[a-z]{3,16}", browser):
        opts["cookiesfrombrowser"] = (browser,)
    return opts


def _import_yt_dlp():
    try:
        import yt_dlp
    except ImportError as exc:  # pragma: no cover - hard dependency
        raise ToolExecutionError("yt-dlp is not installed in the runtime.") from exc
    return yt_dlp


def _friendly_download_error(exc: Exception) -> ToolExecutionError:
    message = str(exc)
    lowered = message.lower()
    if ("confirm you" in lowered and "bot" in lowered) or "sign in" in lowered:
        return ToolExecutionError(
            "The video host asked for a signed-in session. Set the tool's "
            "'cookies_from_browser' config (e.g. 'chrome' or 'firefox') so yt-dlp can "
            f"reuse your browser login. Details: {message[:300]}"
        )
    return ToolExecutionError(f"yt-dlp failed: {message[:500]}")


def _pick_caption_track(info: dict[str, Any], language: str | None) -> tuple[str, str, dict[str, Any]] | None:
    """Return (origin, lang, format) for the best available caption track."""
    manual: dict[str, list[dict]] = info.get("subtitles") or {}
    auto: dict[str, list[dict]] = info.get("automatic_captions") or {}
    manual = {k: v for k, v in manual.items() if k != "live_chat" and v}
    auto = {k: v for k, v in auto.items() if v}
    wanted = (language or info.get("language") or "en").lower()
    base = wanted.split("-")[0]

    def lang_matches(tracks: dict[str, list[dict]], *candidates: str) -> str | None:
        lowered = {k.lower(): k for k in tracks}
        for cand in candidates:
            if cand in lowered:
                return lowered[cand]
        for key_lower, key in lowered.items():
            if key_lower.split("-")[0] == base:
                return key
        return None

    def best_format(formats: list[dict]) -> dict | None:
        by_ext = {str(f.get("ext")): f for f in formats if f.get("url") or f.get("data")}
        for ext in _SUB_EXT_PREFERENCE:
            if ext in by_ext:
                return by_ext[ext]
        return None

    choices: list[tuple[str, dict[str, list[dict]], str | None]] = [
        ("manual_captions", manual, lang_matches(manual, wanted, base)),
        ("auto_captions", auto, lang_matches(auto, f"{base}-orig", wanted, base)),
    ]
    if not language:
        # Unknown language: fall back to whatever original-language track exists.
        orig = next((k for k in auto if k.endswith("-orig")), None)
        choices.append(("manual_captions", manual, next(iter(manual), None)))
        choices.append(("auto_captions", auto, orig))
    for origin, tracks, key in choices:
        if key and (fmt := best_format(tracks[key])):
            return origin, key, fmt
    return None


def _chapters_from_info(info: dict[str, Any]) -> list[Chapter]:
    chapters = []
    for item in info.get("chapters") or []:
        try:
            chapters.append(Chapter(
                str(item.get("title") or "").strip(),
                float(item.get("start_time") or 0.0),
                _float_or_none(item.get("end_time")),
            ))
        except (TypeError, ValueError):
            continue
    return chapters


# Indirection points so tests (and future backends) can replace the network.
CaptionFetcher = Callable[[str, str | None, dict[str, Any]], Transcript | None]
AudioDownloader = Callable[[str, Path, dict[str, Any]], Path]
Transcriber = Callable[[Path, str | None, dict[str, Any]], tuple[list[Segment], str | None]]


def yt_dlp_fetch_captions(url: str, language: str | None, config: dict[str, Any]) -> Transcript | None:
    """Metadata + caption track only; never downloads media."""
    yt_dlp = _import_yt_dlp()
    opts = {**_ydl_base_opts(config), "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not isinstance(info, dict):
                raise ToolExecutionError("yt-dlp returned no metadata for this URL")
            if info.get("_type") == "playlist":
                raise ToolExecutionError("Playlists are not supported; pass a single video URL")
            if info.get("is_live"):
                raise ToolExecutionError("Live streams are not supported; retry once the stream has ended")
            transcript = Transcript(
                source=url,
                title=str(info.get("title") or ""),
                duration=_float_or_none(info.get("duration")),
                language=info.get("language"),
                webpage_url=info.get("webpage_url") or url,
                chapters=_chapters_from_info(info),
            )
            track = _pick_caption_track(info, language)
            if track is None:
                transcript.origin = "none"
                return transcript
            origin, lang, fmt = track
            raw = fmt.get("data")
            if raw is None:
                with ydl.urlopen(fmt["url"]) as response:
                    raw = response.read().decode("utf-8", errors="replace")
            transcript.segments = parse_captions(raw, str(fmt.get("ext") or "vtt"))
            transcript.origin = origin
            transcript.language = lang
            return transcript
    except ToolExecutionError:
        raise
    except Exception as exc:
        raise _friendly_download_error(exc) from exc


def yt_dlp_download_audio(url: str, dest_dir: Path, config: dict[str, Any]) -> Path:
    yt_dlp = _import_yt_dlp()
    dest_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        **_ydl_base_opts(config),
        "format": "bestaudio[abr<=160]/bestaudio/best[height<=360]/best",
        "outtmpl": str(dest_dir / "audio.%(ext)s"),
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                raise ToolExecutionError("yt-dlp returned no metadata for this URL")
            path = Path(ydl.prepare_filename(info))
    except ToolExecutionError:
        raise
    except Exception as exc:
        raise _friendly_download_error(exc) from exc
    if not path.exists():
        candidates = sorted(dest_dir.glob("audio.*"))
        if not candidates:
            raise ToolExecutionError("Audio download finished but no file was written")
        path = candidates[0]
    return path


_WHISPER_MODELS: dict[str, Any] = {}


def faster_whisper_transcribe(path: Path, language: str | None, config: dict[str, Any]) -> tuple[list[Segment], str | None]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise ToolExecutionError(
            "This video has no captions, so it needs local speech-to-text. Install the "
            "optional dependency with `uv sync --extra transcribe` (faster-whisper) in "
            "python-runtime, then retry. Model weights download once on first use."
        ) from exc
    size = str(config.get("whisper_model") or "base")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,48}", size):
        raise ToolExecutionError("Invalid whisper_model config value")
    model = _WHISPER_MODELS.get(size)
    if model is None:
        model = WhisperModel(size, device="auto", compute_type="int8")
        _WHISPER_MODELS[size] = model
    raw_segments, info = model.transcribe(str(path), language=language, vad_filter=True)
    segments = [Segment(float(s.start), float(s.end), s.text.strip()) for s in raw_segments if s.text.strip()]
    return _normalize_segments(segments), getattr(info, "language", language)


def _ffprobe_duration(path: Path) -> float | None:
    import subprocess

    if shutil.which("ffprobe") is None:
        return None
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    return _float_or_none(result.stdout.strip() or None)


def _cache_dir() -> Path:
    path = data_dir() / "cache" / "transcripts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_video_url(url: str) -> str:
    """Drop tracking/timestamp params so equivalent links share one cache entry."""
    parsed = urlparse(url.strip())
    keep = [(k, v) for k, v in parse_qsl(parsed.query) if k not in {"t", "si", "feature", "pp", "start"}
            and not k.startswith("utm_")]
    return urlunparse(parsed._replace(query=urlencode(keep), fragment="")).rstrip("/")


class TranscriptService:
    """Fetch transcripts with a persistent cache shared across runs."""

    def __init__(
        self,
        *,
        caption_fetcher: CaptionFetcher | None = None,
        audio_downloader: AudioDownloader | None = None,
        transcriber: Transcriber | None = None,
        cache_dir: Path | None = None,
    ):
        self.caption_fetcher = caption_fetcher or yt_dlp_fetch_captions
        self.audio_downloader = audio_downloader or yt_dlp_download_audio
        self.transcriber = transcriber or faster_whisper_transcribe
        self._cache_dir = cache_dir

    @property
    def cache_dir(self) -> Path:
        if self._cache_dir is None:
            return _cache_dir()
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        return self._cache_dir

    def _cache_path(self, key: str, language: str | None) -> Path:
        digest = hashlib.sha256(f"{key}|{language or ''}".encode()).hexdigest()[:24]
        return self.cache_dir / f"{digest}.json"

    def _read_cache(self, path: Path) -> Transcript | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if data.get("version") != TRANSCRIPT_CACHE_VERSION:
            return None
        return Transcript.from_dict(data)

    def _write_cache(self, path: Path, transcript: Transcript) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(transcript.to_dict(), ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    def get(
        self,
        source: str,
        *,
        workspace: Any | None,
        language: str | None = None,
        allow_speech_to_text: bool = True,
        config: dict[str, Any] | None = None,
        refresh: bool = False,
    ) -> tuple[Transcript, bool]:
        """Return (transcript, cache_hit)."""
        config = config or {}
        if _is_url(source):
            guard_media_url(source)
            cache_path = self._cache_path("url:" + normalize_video_url(source), language)
        else:
            media_path = resolve_local_media(source, workspace)
            cache_path = self._cache_path("file:" + _file_digest(media_path), language)

        if not refresh and cache_path.exists():
            cached = self._read_cache(cache_path)
            if cached is not None and cached.segments:
                return cached, True

        if _is_url(source):
            transcript = self.caption_fetcher(source, language, config) or Transcript(source=source, origin="none")
            if not transcript.segments:
                if not allow_speech_to_text:
                    raise ToolExecutionError(
                        "No captions are available for this video. Retry with "
                        "allow_speech_to_text=true to transcribe the audio locally."
                    )
                if transcript.duration and transcript.duration > MAX_WHISPER_SOURCE_SECONDS:
                    raise ToolExecutionError("Video is longer than the 4h speech-to-text limit")
                with tempfile.TemporaryDirectory(prefix="agentforge-audio-") as tmp:
                    audio = self.audio_downloader(source, Path(tmp), config)
                    segments, detected = self.transcriber(audio, language, config)
                transcript.segments = segments
                transcript.language = detected or transcript.language
                transcript.origin = "whisper"
        else:
            media_path = resolve_local_media(source, workspace)
            if not allow_speech_to_text:
                raise ToolExecutionError("Local files need speech-to-text; set allow_speech_to_text=true")
            segments, detected = self.transcriber(media_path, language, config)
            transcript = Transcript(
                source=source,
                title=media_path.stem,
                duration=_ffprobe_duration(media_path),
                language=detected,
                origin="whisper",
                segments=segments,
            )

        if not transcript.segments:
            raise ToolExecutionError("No speech was found in this video, so there is nothing to search")
        self._write_cache(cache_path, transcript)
        return transcript, False


def resolve_local_media(source: str, workspace: Any | None) -> Path:
    if workspace is None:
        raise ToolExecutionError("Local media paths need a run workspace")
    try:
        path = workspace.resolve(source)
    except Exception as exc:
        raise ToolExecutionError(f"Unsafe workspace path: {source}") from exc
    if not path.is_file():
        raise ToolExecutionError(f"Workspace file does not exist: {source}")
    if path.suffix.lower() not in _LOCAL_MEDIA_SUFFIXES:
        raise ToolExecutionError(f"Unsupported media type: {path.suffix or 'none'}")
    return path


def _slug(text: str, fallback: str = "video") -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()[:48]
    return slug or fallback


def save_transcript_to_workspace(transcript: Transcript, workspace: Any) -> str:
    slug = _slug(transcript.title) + "-" + hashlib.sha256(transcript.source.encode()).hexdigest()[:8]
    path = workspace.resolve(f"video/{slug}.transcript.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(transcript.to_dict(), ensure_ascii=False), encoding="utf-8")
    return workspace.relative(path)


def load_workspace_transcript(rel: str, workspace: Any) -> Transcript:
    try:
        path = workspace.resolve(rel)
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ToolExecutionError) as exc:
        raise ToolExecutionError(f"Could not read transcript file: {rel}") from exc
    transcript = Transcript.from_dict(data)
    if not transcript.segments:
        raise ToolExecutionError(f"Transcript file has no segments: {rel}")
    return transcript


# ---------------------------------------------------------------------------
# Outline rendering
# ---------------------------------------------------------------------------


def render_outline(transcript: Transcript, *, line_seconds: float = 30.0, offset: int = 0,
                   max_chars: int = DEFAULT_OUTLINE_CHARS) -> tuple[str, int | None]:
    """Compact "[m:ss] text" lines; returns (page, next_offset)."""
    lines: list[str] = []
    bucket: list[str] = []
    bucket_start: float | None = None
    for seg in transcript.segments:
        if bucket_start is None:
            bucket_start = seg.start
        bucket.append(seg.text)
        if seg.end - bucket_start >= line_seconds:
            lines.append(f"[{format_timestamp(bucket_start)}] {' '.join(bucket)}")
            bucket, bucket_start = [], None
    if bucket and bucket_start is not None:
        lines.append(f"[{format_timestamp(bucket_start)}] {' '.join(bucket)}")

    full = "\n".join(lines)
    if offset >= len(full):
        return "", None
    page = full[offset: offset + max_chars]
    end = offset + len(page)
    if end < len(full):
        cut = page.rfind("\n")
        if cut > 0:
            page = page[:cut]
            end = offset + cut + 1
        return page, end
    return page, None


# ---------------------------------------------------------------------------
# Clip ranking
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"[\w']+", re.UNICODE)
_STOPWORDS = frozenset("""
a about above after again against all am an and any are as at be because been before being below
between both but by can could did do does doing down during each few for from further had has have
having he her here hers herself him himself his how i if in into is it its itself just me more most
my myself no nor not now of off on once only or other our ours ourselves out over own same she should
so some such than that the their theirs them themselves then there these they this those through to
too under until up very was we were what when where which while who whom why will with would you your
yours yourself yourselves um uh like yeah okay oh gonna wanna kinda really thing things get got going
know mean say said part where clip clips moment moments video talks talk talking discuss discusses
""".split())


def _stem(word: str) -> str:
    for suffix in ("ingly", "edly", "ing", "ies", "ied", "ed", "es", "ly", "s"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            base = word[: -len(suffix)]
            return base + "y" if suffix in {"ies", "ied"} else base
    return word


def tokenize(text: str) -> list[str]:
    tokens = []
    for raw in _WORD_RE.findall(text.lower()):
        word = raw.strip("'").replace("'", "")
        if len(word) < 2 or word in _STOPWORDS:
            continue
        tokens.append(_stem(word))
    return tokens


@dataclass
class _Window:
    first: int
    last: int
    start: float
    end: float
    text: str
    tokens: list[str]


def _build_windows(segments: list[Segment], window_seconds: float) -> list[_Window]:
    windows: list[_Window] = []
    n = len(segments)
    last_start = -math.inf
    for i in range(n):
        # Start a new window at most every third of a window to bound the count.
        if segments[i].start - last_start < window_seconds / 3:
            continue
        last_start = segments[i].start
        j = i
        while j + 1 < n and segments[j + 1].end - segments[i].start <= window_seconds:
            j += 1
        text = " ".join(s.text for s in segments[i: j + 1])
        windows.append(_Window(i, j, segments[i].start, segments[j].end, text, tokenize(text)))
    return windows


def _chapter_for(transcript: Transcript, t: float) -> Chapter | None:
    current = None
    for chapter in transcript.chapters:
        if chapter.start <= t:
            current = chapter
        else:
            break
    return current


@dataclass
class ClipCandidate:
    start: float
    end: float
    score: float
    excerpt: str
    matched_terms: list[str]
    chapter: str | None


def find_clips(
    transcript: Transcript,
    query: str,
    *,
    keywords: list[str] | None = None,
    max_clips: int = 5,
    min_seconds: float = 15.0,
    max_seconds: float = 90.0,
    padding: float = 1.5,
) -> list[ClipCandidate]:
    segments = transcript.segments
    if not segments:
        return []
    query_terms = tokenize(query)
    extra_terms = [t for kw in keywords or [] for t in tokenize(kw)]
    weights: dict[str, float] = {}
    for term in query_terms:
        weights[term] = max(weights.get(term, 0.0), 1.0)
    for term in extra_terms:
        weights[term] = max(weights.get(term, 0.0), 0.7)
    if not weights:
        raise ToolExecutionError("The query has no searchable words; describe the moment or pass keywords")

    window_seconds = max(min_seconds, min(max_seconds, 45.0))
    windows = _build_windows(segments, window_seconds)
    doc_freq: Counter[str] = Counter()
    for window in windows:
        doc_freq.update(set(window.tokens))
    avg_len = sum(len(w.tokens) for w in windows) / max(1, len(windows)) or 1.0
    n_docs = len(windows)
    k1, b = 1.4, 0.75

    phrases = [p for p in [query.strip().lower(), *(kw.strip().lower() for kw in keywords or [])]
               if len(p.split()) >= 2]
    scored: list[tuple[float, _Window, list[str]]] = []
    for window in windows:
        tf = Counter(window.tokens)
        score = 0.0
        matched = []
        for term, weight in weights.items():
            freq = tf.get(term, 0)
            if not freq:
                continue
            matched.append(term)
            idf = math.log(1 + (n_docs - doc_freq[term] + 0.5) / (doc_freq[term] + 0.5))
            score += weight * idf * freq * (k1 + 1) / (freq + k1 * (1 - b + b * len(window.tokens) / avg_len))
        if not matched:
            continue
        # Reward windows that cover more distinct query ideas, not one repeated word.
        score *= 0.5 + 0.5 * len(matched) / len(weights)
        lowered = window.text.lower()
        if any(p in lowered for p in phrases):
            score *= 1.6
        chapter = _chapter_for(transcript, window.start)
        if chapter and set(tokenize(chapter.title)) & weights.keys():
            score *= 1.3
        scored.append((score, window, matched))

    scored.sort(key=lambda item: item[0], reverse=True)
    picked: list[tuple[float, _Window, list[str]]] = []
    for item in scored:
        _, window, _ = item
        if any(window.start < other.end + padding and other.start < window.end + padding for _, other, _ in picked):
            continue
        picked.append(item)
        if len(picked) >= max_clips:
            break
    if not picked:
        return []

    top = picked[0][0] or 1.0
    end_limit = transcript.end_time
    clips: list[ClipCandidate] = []
    for score, window, matched in picked:
        first, last = window.first, window.last
        # Grow to the minimum length by alternately adding neighbouring segments.
        while segments[last].end - segments[first].start < min_seconds:
            grew = False
            if last + 1 < len(segments):
                last += 1
                grew = True
            if segments[last].end - segments[first].start < min_seconds and first > 0:
                first -= 1
                grew = True
            if not grew:
                break
        while last > first and segments[last].end - segments[first].start > max_seconds:
            last -= 1
        start = max(0.0, segments[first].start - padding)
        end = segments[last].end + padding
        if end_limit:
            end = min(end, end_limit)
        excerpt = " ".join(s.text for s in segments[first: last + 1])
        chapter = _chapter_for(transcript, segments[first].start)
        clips.append(ClipCandidate(
            start=round(start, 2),
            end=round(end, 2),
            score=round(score / top, 3),
            excerpt=excerpt if len(excerpt) <= 320 else excerpt[:317].rsplit(" ", 1)[0] + "...",
            matched_terms=sorted(matched),
            chapter=chapter.title if chapter else None,
        ))
    return clips


def timestamp_url(url: str | None, seconds: float) -> str | None:
    if not url:
        return None
    host = urlparse(url).hostname or ""
    if not any(h in host for h in ("youtube.com", "youtu.be")):
        return None
    parsed = urlparse(url)
    query = [(k, v) for k, v in parse_qsl(parsed.query) if k != "t"] + [("t", f"{int(seconds)}s")]
    return urlunparse(parsed._replace(query=urlencode(query)))


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

SectionDownloader = Callable[[str, float, float, Path, dict[str, Any], Callable[[], None]], Path]


def yt_dlp_download_section(url: str, start: float, end: float, out_stem: Path,
                            config: dict[str, Any], check_cancel: Callable[[], None]) -> Path:
    yt_dlp = _import_yt_dlp()
    from yt_dlp.utils import download_range_func

    max_height = int(config.get("max_height") or 720)

    def hook(_status: dict) -> None:
        check_cancel()

    opts = {
        **_ydl_base_opts(config),
        "format": f"bv*[height<={max_height}]+ba/b[height<={max_height}]/bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": str(out_stem) + ".%(ext)s",
        "download_ranges": download_range_func(None, [(start, end)]),
        # Frame-exact cuts re-encode; name the encoder instead of relying on ffmpeg's
        # default, which is MPEG-4 Part 2 (unplayable in Chromium) without libx264.
        "force_keyframes_at_cuts": True,
        "external_downloader_args": {
            "ffmpeg_o": [*h264_args(bitrate=bitrate_for_height(max_height)), "-c:a", "aac", "-b:a", "160k"],
        },
        "progress_hooks": [hook],
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if isinstance(info, dict) and info.get("_type") == "playlist":
                raise ToolExecutionError("Playlists are not supported; pass a single video URL")
    except (ToolExecutionError, asyncio.CancelledError):
        raise
    except Exception as exc:
        raise _friendly_download_error(exc) from exc
    matches = sorted(out_stem.parent.glob(out_stem.name + ".*"))
    matches = [m for m in matches if m.suffix.lower() in {".mp4", ".mkv", ".webm"}]
    if not matches:
        raise ToolExecutionError("yt-dlp finished but no clip file was written")
    return matches[0]


async def ffmpeg_cut(source: Path, start: float, end: float, out_path: Path, cancel: Any) -> Path:
    if shutil.which("ffmpeg") is None:
        raise ToolExecutionError("ffmpeg is required to cut clips; install it and put it on PATH")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start:.3f}", "-i", str(source), "-t", f"{end - start:.3f}",
        "-map", "0:v:0?", "-map", "0:a:0?",
        *h264_args(bitrate=bitrate_for_height(720)),
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out_path),
    ]
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    communicate = asyncio.ensure_future(proc.communicate())
    try:
        while not communicate.done():
            if getattr(cancel, "cancelled", False):
                proc.kill()
                raise asyncio.CancelledError()
            await asyncio.wait({communicate}, timeout=0.5)
        _, stderr = communicate.result()
    except BaseException:
        if proc.returncode is None:
            proc.kill()
        raise
    if proc.returncode != 0:
        raise ToolExecutionError(f"ffmpeg failed: {stderr.decode(errors='replace')[-500:]}")
    return out_path


def write_clip_srt(transcript: Transcript, start: float, end: float, path: Path) -> bool:
    entries = []
    for seg in transcript.segments:
        if seg.end <= start or seg.start >= end:
            continue
        s = max(seg.start, start) - start
        e = min(seg.end, end) - start
        entries.append(f"{len(entries) + 1}\n{_srt_time(s)} --> {_srt_time(e)}\n{seg.text}\n")
    if not entries:
        return False
    path.write_text("\n".join(entries), encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# v2 tools
# ---------------------------------------------------------------------------

_SHARED_SERVICE = TranscriptService()


def _config(ctx: Any) -> dict[str, Any]:
    config = getattr(ctx, "config", None)
    return config if isinstance(config, dict) else {}


def _raise_if_cancelled(ctx: Any) -> None:
    cancel = getattr(ctx, "cancel", None)
    if cancel is not None and getattr(cancel, "cancelled", False):
        raise asyncio.CancelledError()


def _as_tool_error(exc: ToolExecutionError) -> ToolError:
    return ToolError(str(exc))


class VideoTranscriptInput(BaseModel):
    source: str = Field(description="Video page URL (YouTube, Vimeo, any yt-dlp site) or a workspace-relative media file path.")
    language: str | None = Field(default=None, description="Caption language code such as 'en' or 'es'. Omit to use the video's own language.")
    include_outline: bool = Field(default=False, description="Also return a compact '[m:ss] text' outline of the transcript (about 12k tokens per hour of speech, paged).")
    offset: int = Field(default=0, ge=0, description="Outline page offset; use next_offset from the previous call.")
    allow_speech_to_text: bool = Field(default=True, description="When no captions exist, transcribe the audio locally (downloads audio only).")
    refresh: bool = Field(default=False, description="Ignore the transcript cache.")


class VideoTranscriptTool(Tool):
    kind: ClassVar[str] = "video_transcript"
    name: ClassVar[str] = "video_transcript"
    description: ClassVar[str] = "Get a timestamped transcript and chapters for a video."
    default_description: ClassVar[str] = (
        "Get the timestamped transcript and chapter list of a video WITHOUT watching or downloading it. "
        "Uses the video's captions when available and local speech-to-text otherwise; results are cached. "
        "Returns title, duration, chapters and a transcript_path you can pass to clip_finder. "
        "Set include_outline=true only when you need to read the content yourself."
    )
    Input: ClassVar[type[BaseModel]] = VideoTranscriptInput
    permissions: ClassVar[set] = {"net"}

    def __init__(self, service: TranscriptService | None = None):
        self.service = service or _SHARED_SERVICE

    async def run(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        assert isinstance(args, VideoTranscriptInput)
        _raise_if_cancelled(ctx)
        try:
            transcript, cache_hit = await asyncio.to_thread(
                self.service.get, args.source.strip(), workspace=ctx.workspace, language=args.language,
                allow_speech_to_text=args.allow_speech_to_text, config=_config(ctx), refresh=args.refresh,
            )
            rel = save_transcript_to_workspace(transcript, ctx.workspace)
        except ToolExecutionError as exc:
            raise _as_tool_error(exc) from exc

        summary: dict[str, Any] = {
            "title": transcript.title,
            "duration": format_timestamp(transcript.end_time),
            "duration_seconds": round(transcript.end_time, 1),
            "transcript_origin": transcript.origin,
            "language": transcript.language,
            "segments": len(transcript.segments),
            "cached": cache_hit,
            "transcript_path": rel,
            "chapters": [{"start": format_timestamp(c.start), "title": c.title} for c in transcript.chapters[:60]],
        }
        next_offset = None
        if args.include_outline:
            outline, next_offset = render_outline(transcript, offset=args.offset,
                                                  max_chars=DEFAULT_OUTLINE_CHARS - 600)
            summary["outline"] = outline
            summary["next_offset"] = next_offset
        content = json.dumps(summary, ensure_ascii=False, indent=1)
        return ToolResult(
            content=content,
            data={"transcript_path": rel, "origin": transcript.origin},
            truncated=next_offset is not None,
            next_offset=next_offset,
        )


class ClipFinderInput(BaseModel):
    query: str = Field(description="What the clip should contain, in plain words, e.g. 'the host explains why the bridge collapsed'.")
    source: str | None = Field(default=None, description="Video URL or workspace media path. Not needed when transcript_path is given.")
    transcript_path: str | None = Field(default=None, description="transcript_path returned by video_transcript (avoids refetching).")
    keywords: list[str] = Field(default_factory=list, max_length=30, description="Synonyms, names and phrases likely to be SPOKEN in the moment. Strongly improves recall.")
    max_clips: int = Field(default=5, ge=1, le=MAX_CLIPS_PER_CALL)
    min_seconds: float = Field(default=15.0, ge=1.0, le=MAX_CLIP_SECONDS)
    max_seconds: float = Field(default=90.0, ge=5.0, le=MAX_CLIP_SECONDS)
    padding_seconds: float = Field(default=1.5, ge=0.0, le=15.0, description="Extra lead-in/lead-out around speech.")
    language: str | None = None


class ClipFinderTool(Tool):
    kind: ClassVar[str] = "clip_finder"
    name: ClassVar[str] = "clip_finder"
    description: ClassVar[str] = "Find the timestamps of moments in a video that match a description."
    default_description: ClassVar[str] = (
        "Find the start/end timestamps of moments in a video that match a description, by searching its "
        "transcript locally (no video watching, near-zero token cost). Pass a source URL or a transcript_path, "
        "a query, and keywords: words/names/phrases the speaker would actually SAY. Returns ranked candidate "
        "clips with excerpts; read the excerpts to confirm, then pass the chosen start/end to clip_extractor."
    )
    Input: ClassVar[type[BaseModel]] = ClipFinderInput
    permissions: ClassVar[set] = {"net"}

    def __init__(self, service: TranscriptService | None = None):
        self.service = service or _SHARED_SERVICE

    async def run(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        assert isinstance(args, ClipFinderInput)
        _raise_if_cancelled(ctx)
        if args.min_seconds > args.max_seconds:
            raise ToolError("min_seconds must not exceed max_seconds")
        try:
            if args.transcript_path:
                transcript = load_workspace_transcript(args.transcript_path, ctx.workspace)
            elif args.source:
                transcript, _ = await asyncio.to_thread(
                    self.service.get, args.source.strip(), workspace=ctx.workspace,
                    language=args.language, config=_config(ctx),
                )
            else:
                raise ToolExecutionError("Pass either source or transcript_path")
            clips = find_clips(
                transcript, args.query, keywords=args.keywords, max_clips=args.max_clips,
                min_seconds=args.min_seconds, max_seconds=args.max_seconds, padding=args.padding_seconds,
            )
        except ToolExecutionError as exc:
            raise _as_tool_error(exc) from exc

        source = transcript.webpage_url or transcript.source
        payload = {
            "source": source,
            "title": transcript.title,
            "duration": format_timestamp(transcript.end_time),
            "clips": [
                {
                    "rank": idx + 1,
                    "start": clip.start,
                    "end": clip.end,
                    "range": f"{format_timestamp(clip.start)}-{format_timestamp(clip.end)}",
                    "seconds": round(clip.end - clip.start, 1),
                    "relevance": clip.score,
                    "chapter": clip.chapter,
                    "matched": clip.matched_terms,
                    "excerpt": clip.excerpt,
                    **({"link": link} if (link := timestamp_url(transcript.webpage_url, clip.start)) else {}),
                }
                for idx, clip in enumerate(clips)
            ],
        }
        if not clips:
            payload["hint"] = (
                "No transcript window matched. Retry with more keywords (synonyms, names, phrasing a "
                "speaker would use), or call video_transcript with include_outline=true to read it."
            )
        return ToolResult(content=json.dumps(payload, ensure_ascii=False, indent=1), data=payload)


class ClipSpec(BaseModel):
    start: float | str = Field(description="Start time in seconds or H:MM:SS.")
    end: float | str = Field(description="End time in seconds or H:MM:SS.")
    label: str | None = Field(default=None, max_length=80, description="Short name used in the output filename.")

    @field_validator("start", "end")
    @classmethod
    def _valid_time(cls, value: float | str) -> float:
        try:
            return parse_timestamp(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


class ClipExtractorInput(BaseModel):
    source: str = Field(description="Video URL or workspace-relative media path.")
    clips: list[ClipSpec] = Field(min_length=1, max_length=MAX_CLIPS_PER_CALL)
    subtitles: bool = Field(default=False, description="Also write an .srt file per clip from the transcript.")
    transcript_path: str | None = Field(default=None, description="transcript_path from video_transcript, used for subtitles.")


class ClipExtractorTool(Tool):
    kind: ClassVar[str] = "clip_extractor"
    name: ClassVar[str] = "clip_extractor"
    description: ClassVar[str] = "Cut clips from a video by timestamp, downloading only those sections."
    default_description: ClassVar[str] = (
        "Cut one or more clips out of a video by start/end time and save them as MP4 files. For URLs only the "
        "requested sections are downloaded (not the whole video). Use timestamps from clip_finder."
    )
    Input: ClassVar[type[BaseModel]] = ClipExtractorInput
    permissions: ClassVar[set] = {"net", "subprocess"}

    def __init__(self, section_downloader: SectionDownloader | None = None, service: TranscriptService | None = None):
        self.section_downloader = section_downloader or yt_dlp_download_section
        self.service = service or _SHARED_SERVICE

    async def run(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        assert isinstance(args, ClipExtractorInput)
        source = args.source.strip()
        ranges: list[tuple[float, float, str]] = []
        for idx, clip in enumerate(args.clips, 1):
            start, end = float(clip.start), float(clip.end)
            if end <= start:
                raise ToolError(f"Clip {idx}: end must be after start")
            if end - start > MAX_CLIP_SECONDS:
                raise ToolError(f"Clip {idx} is longer than {int(MAX_CLIP_SECONDS)}s")
            ranges.append((start, end, clip.label or f"clip-{idx}"))
        if sum(e - s for s, e, _ in ranges) > MAX_TOTAL_CLIP_SECONDS:
            raise ToolError(f"Total clip length exceeds {int(MAX_TOTAL_CLIP_SECONDS)}s for one call")

        transcript = None
        if args.subtitles:
            try:
                if args.transcript_path:
                    transcript = load_workspace_transcript(args.transcript_path, ctx.workspace)
                else:
                    transcript, _ = await asyncio.to_thread(
                        self.service.get, source, workspace=ctx.workspace, config=_config(ctx),
                    )
            except ToolExecutionError as exc:
                raise _as_tool_error(exc) from exc

        is_url = _is_url(source)
        try:
            if is_url:
                guard_media_url(source)
                if shutil.which("ffmpeg") is None:
                    raise ToolExecutionError("ffmpeg is required to cut clips; install it and put it on PATH")
                local = None
            else:
                local = resolve_local_media(source, ctx.workspace)
        except ToolExecutionError as exc:
            raise _as_tool_error(exc) from exc

        def check_cancel() -> None:
            _raise_if_cancelled(ctx)

        artifacts: list[ArtifactRef] = []
        results = []
        for idx, (start, end, label) in enumerate(ranges, 1):
            _raise_if_cancelled(ctx)
            name = f"{idx:02d}-{_slug(label, 'clip')}-{int(start)}s"
            target = ctx.workspace.new_path(f"clips/{name}.mp4")
            try:
                if is_url:
                    produced = await asyncio.to_thread(
                        self.section_downloader, source, start, end, target.with_suffix(""), _config(ctx), check_cancel,
                    )
                else:
                    assert local is not None
                    produced = await ffmpeg_cut(local, start, end, target, getattr(ctx, "cancel", None))
            except ToolExecutionError as exc:
                raise _as_tool_error(exc) from exc
            rel = ctx.workspace.relative(produced)
            entry = {"file": rel, "start": start, "end": end,
                     "range": f"{format_timestamp(start)}-{format_timestamp(end)}"}
            artifacts.append(ArtifactRef(path=rel, mime="video/mp4", description=f"{label} ({entry['range']})"))
            if transcript is not None:
                srt = produced.with_suffix(".srt")
                if write_clip_srt(transcript, start, end, srt):
                    entry["subtitles"] = ctx.workspace.relative(srt)
                    artifacts.append(ArtifactRef(path=entry["subtitles"], mime="application/x-subrip",
                                                 description=f"Subtitles for {label}"))
            results.append(entry)

        return ToolResult(
            content=json.dumps({"clips": results}, ensure_ascii=False, indent=1),
            artifacts=artifacts,
            data={"clips": results},
        )
