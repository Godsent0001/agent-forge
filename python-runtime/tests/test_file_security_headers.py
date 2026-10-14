from pathlib import Path

from app.infra.file_security import file_response_headers


def test_active_content_is_downloaded_and_sandboxed():
    headers = file_response_headers(Path("preview.SVG"))
    assert headers["Content-Disposition"] == "attachment"
    assert headers["Content-Security-Policy"] == "default-src 'none'; sandbox"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Cache-Control"] == "no-store"


def test_binary_artifacts_are_non_cacheable_and_non_sniffable_without_forcing_download():
    headers = file_response_headers(Path("render.mp4"))
    assert "Content-Disposition" not in headers
    assert "Content-Security-Policy" not in headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Cross-Origin-Resource-Policy"] == "same-origin"
