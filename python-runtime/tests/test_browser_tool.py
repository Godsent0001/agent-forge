from __future__ import annotations

from app.tools.browser import BrowserTool


class FakeHttpTool:
    async def execute(self, input: str, *, context):
        assert input == "GET https://example.com/docs"
        return (
            "Status: 200\nHeaders:\ncontent-type: text/html\nBody:\n"
            "<html><head><title>AgentForge Docs</title><style>.x{}</style></head>"
            "<body><h1>Setup</h1><script>alert('not text')</script><p>Install the runtime.</p></body></html>"
            "\ntruncated: false"
        )


async def test_browser_extracts_title_and_readable_text():
    result = await BrowserTool(http_tool=FakeHttpTool()).execute(
        "https://example.com/docs", context=None
    )

    assert "Title: AgentForge Docs" in result
    assert "Setup" in result
    assert "Install the runtime." in result
    assert "alert(" not in result
