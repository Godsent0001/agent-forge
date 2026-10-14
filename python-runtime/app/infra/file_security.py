"""Security headers for user/tool-generated files served by the local sidecar."""
from __future__ import annotations

from pathlib import Path

ACTIVE_CONTENT_SUFFIXES = frozenset({
    ".html", ".htm", ".svg", ".js", ".mjs", ".css", ".xml", ".xhtml", ".xsl",
})


def file_response_headers(path: Path) -> dict[str, str]:
    """Return non-cacheable, non-sniffable headers; force active content to download."""
    headers = {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Cross-Origin-Resource-Policy": "same-origin",
        "Referrer-Policy": "no-referrer",
    }
    if path.suffix.lower() in ACTIVE_CONTENT_SUFFIXES:
        headers["Content-Disposition"] = "attachment"
        headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return headers
