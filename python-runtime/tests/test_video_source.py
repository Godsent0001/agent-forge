import json

import pytest

from app.tools.video_source import VideoSourceTool


@pytest.mark.asyncio
async def test_video_source_returns_structured_candidates():
    def fake_search(query: str, limit: int):
        assert query == "history documentary"
        assert limit == 3
        return [
            {
                "id": "abc",
                "title": "History Documentary",
                "url": "https://example.com/video",
                "duration": 120,
                "uploader": "Example",
                "thumbnail": None,
                "source": "example",
            }
        ]

    tool = VideoSourceTool(search_fn=fake_search)
    result = json.loads(await tool.execute('{"query":"history documentary","limit":3}', context=None))

    assert result[0]["id"] == "abc"
    assert result[0]["url"] == "https://example.com/video"


@pytest.mark.asyncio
async def test_video_source_rejects_empty_query():
    tool = VideoSourceTool(search_fn=lambda query, limit: [])
    with pytest.raises(Exception, match="non-empty"):
        await tool.execute(" ", context=None)


@pytest.mark.asyncio
async def test_video_source_clamps_result_limit():
    seen = {}

    def fake_search(query: str, limit: int):
        seen["limit"] = limit
        return []

    tool = VideoSourceTool(search_fn=fake_search)
    await tool.execute('{"query":"clips","limit":99}', context=None)

    assert seen["limit"] == 10


def test_yt_dlp_backend_uses_search_prefix_and_metadata(monkeypatch):
    import sys
    import types

    calls = {}

    class FakeYoutubeDL:
        def __init__(self, opts):
            calls["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, target, download):
            calls["target"] = target
            calls["download"] = download
            return {
                "entries": [
                    {
                        "id": "video-1",
                        "title": "Example clip",
                        "webpage_url": "https://example.com/video-1",
                        "duration": 42,
                        "uploader": "Example",
                        "thumbnail": "https://example.com/thumb.jpg",
                        "extractor_key": "Example",
                    }
                ]
            }

    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=FakeYoutubeDL))

    from app.tools.video_source import _yt_dlp_search

    result = _yt_dlp_search("history clip", 3)

    assert calls["target"] == "ytsearch3:history clip"
    assert calls["download"] is False
    assert calls["opts"]["skip_download"] is True
    assert calls["opts"]["noplaylist"] is True
    assert result[0]["title"] == "Example clip"
    assert result[0]["url"] == "https://example.com/video-1"


def test_yt_dlp_backend_accepts_direct_urls(monkeypatch):
    import sys
    import types

    calls = {}

    class FakeYoutubeDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, target, download):
            calls["target"] = target
            return {
                "id": "direct-1",
                "title": "Direct video",
                "webpage_url": target,
            }

    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=FakeYoutubeDL))

    from app.tools.video_source import _yt_dlp_search

    result = _yt_dlp_search("https://example.com/video", 1)

    assert calls["target"] == "https://example.com/video"
    assert result[0]["id"] == "direct-1"
