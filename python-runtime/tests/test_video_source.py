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
