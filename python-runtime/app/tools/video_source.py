"""Video source tool backed by yt-dlp.

Searches supported video hosts for clip candidates and returns stable metadata.
The tool does not download media; pass a returned URL to video_transcript /
clip_finder / clip_extractor (app/tools/video_clips.py) to locate and cut clips.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

from app.infra.ssrf import UnsafeURL, assert_public_url
from app.tools.base import Tool, ToolExecutionError

SearchFn = Callable[[str, int], list[dict[str, Any]]]


def guard_media_url(url: str) -> None:
    """Reject URLs that would make yt-dlp fetch localhost/private services."""
    try:
        raw_port = os.environ.get("AGENTFORGE_PORT") or os.environ.get("PORT") or "8000"
        runtime_port = int(raw_port)
    except (TypeError, ValueError):
        runtime_port = 8000
    try:
        assert_public_url(url, app_port=runtime_port)
    except UnsafeURL as exc:
        raise ToolExecutionError(str(exc)) from exc


def _yt_dlp_search(query: str, limit: int) -> list[dict[str, Any]]:
    parsed = urlparse(query)
    if parsed.scheme.lower() in {"http", "https"}:
        guard_media_url(query)
        search_target = query
    else:
        search_target = f"ytsearch{limit}:{query}"

    try:
        import yt_dlp
    except ImportError as exc:
        raise ToolExecutionError(
            "video_source requires yt-dlp. Install the runtime dependency first."
        ) from exc
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 30,
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(search_target, download=False)
            entries = info.get("entries") if isinstance(info, dict) else None
            if entries is None:
                entries = [info]

            results: list[dict[str, Any]] = []
            for entry in entries:
                if not entry:
                    continue
                results.append({
                    "id": entry.get("id"),
                    "title": entry.get("title") or "",
                    "url": entry.get("webpage_url") or entry.get("original_url") or "",
                    "duration": entry.get("duration"),
                    "uploader": entry.get("uploader") or entry.get("channel"),
                    "thumbnail": entry.get("thumbnail"),
                    "source": entry.get("extractor_key") or entry.get("extractor"),
                })
                if len(results) >= limit:
                    break
            return results
    except Exception as exc:
        raise ToolExecutionError(f"video_source backend failed: {exc}") from exc


class VideoSourceTool(Tool):
    name = "video_source"
    description = "Find video clips across yt-dlp-supported hosts and return source metadata."

    def __init__(self, search_fn: SearchFn | None = None):
        self._search_fn = search_fn or _yt_dlp_search

    async def execute(self, input: str, *, context: Any) -> str:
        query = input.strip()
        limit = 5

        if query.startswith("{"):
            try:
                payload = json.loads(query)
            except json.JSONDecodeError as exc:
                raise ToolExecutionError("video_source JSON input is invalid") from exc
            query = str(payload.get("query", "")).strip()
            try:
                limit = int(payload.get("limit", 5))
            except (TypeError, ValueError) as exc:
                raise ToolExecutionError("video_source limit must be an integer") from exc

        if not query:
            raise ToolExecutionError("video_source requires a non-empty query")

        limit = max(1, min(limit, 10))
        results = await asyncio.to_thread(self._search_fn, query, limit)
        return json.dumps(results[:limit], ensure_ascii=False)
