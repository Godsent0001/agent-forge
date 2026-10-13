from __future__ import annotations

import pytest

from app.tools.base import ToolExecutionError
from app.tools.video_source import _yt_dlp_search


def test_video_source_rejects_loopback_url_before_network_lookup():
    with pytest.raises(ToolExecutionError, match="private|local"):
        _yt_dlp_search("http://127.0.0.1:8000/health", 5)


def test_video_source_rejects_local_hostname_before_network_lookup():
    with pytest.raises(ToolExecutionError, match="[Ll]ocal"):
        _yt_dlp_search("http://localhost/", 5)
