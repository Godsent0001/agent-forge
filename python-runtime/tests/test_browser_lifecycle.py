from __future__ import annotations

import asyncio

import pytest

from app.tools import browser as browser_module


class _FakeBrowser:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _FakePlaywright:
    def __init__(self) -> None:
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True


@pytest.mark.asyncio
async def test_close_browser_session_releases_browser_and_expiry_task() -> None:
    execution_id = "browser-lifecycle-test"
    browser = _FakeBrowser()
    playwright = _FakePlaywright()
    expiry = asyncio.create_task(asyncio.sleep(60))
    browser_module._BROWSER_SESSIONS[execution_id] = (playwright, browser, object())
    browser_module._BROWSER_SESSION_EXPIRY[execution_id] = expiry

    await browser_module.close_browser_session(execution_id)

    assert browser.closed
    assert playwright.stopped
    assert expiry.cancelled()
    assert execution_id not in browser_module._BROWSER_SESSIONS
    assert execution_id not in browser_module._BROWSER_SESSION_EXPIRY



@pytest.mark.asyncio
async def test_browser_process_cleanup_finishes_before_cancellation_propagates() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class _SlowBrowser(_FakeBrowser):
        async def close(self) -> None:
            started.set()
            await release.wait()
            self.closed = True

    execution_id = "browser-cancel-cleanup-test"
    browser = _SlowBrowser()
    playwright = _FakePlaywright()
    browser_module._BROWSER_SESSIONS[execution_id] = (playwright, browser, object())

    closing = asyncio.create_task(browser_module.close_browser_session(execution_id))
    await started.wait()
    closing.cancel()
    await asyncio.sleep(0)
    assert not closing.done(), "cancellation must not interrupt browser process teardown"

    release.set()
    with pytest.raises(asyncio.CancelledError):
        await closing

    assert browser.closed
    assert playwright.stopped
    assert execution_id not in browser_module._BROWSER_SESSIONS
