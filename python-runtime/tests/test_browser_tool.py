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


async def test_browser_retries_transient_navigation_failure():
    from app.tools.browser import _navigate_page

    class FakePage:
        def __init__(self):
            self.calls = []
        async def goto(self, url, *, wait_until, timeout):
            self.calls.append((url, wait_until, timeout))
            if len(self.calls) == 1:
                raise RuntimeError("Timeout 20000ms exceeded")

    page = FakePage()
    await _navigate_page(page, "https://www.google.com")
    assert [call[1] for call in page.calls] == ["domcontentloaded", "commit"]


async def test_browser_does_not_retry_non_transient_navigation_failure():
    import pytest
    from app.tools.browser import _navigate_page

    class FakePage:
        calls = 0
        async def goto(self, url, *, wait_until, timeout):
            self.calls += 1
            raise RuntimeError("net::ERR_CERT_AUTHORITY_INVALID is not recoverable")

    page = FakePage()
    with pytest.raises(RuntimeError, match="ERR_CERT_AUTHORITY_INVALID"):
        await _navigate_page(page, "https://example.com")
    assert page.calls == 1
