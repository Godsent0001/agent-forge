"""JavaScript-capable browser automation with SSRF checks on every request."""
from __future__ import annotations

import asyncio
import os
import sys
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

from app.infra.ssrf import UnsafeURL, assert_public_url
from app.tools.base import Tool, ToolExecutionError

MAX_PAGE_TEXT_CHARS = 10_000
NAVIGATION_TIMEOUT_MS = 20_000
MAX_BROWSER_SESSIONS = 2

# Browser processes are expensive. Share one bounded registry across tool
# instances and explicitly close a run's session when its execution finishes.
_BROWSER_SESSIONS: dict[str, tuple[Any, Any, Any]] = {}
_BROWSER_SESSION_EXPIRY: dict[str, asyncio.Task] = {}
_BROWSER_SESSION_LOCK = asyncio.Lock()


async def close_browser_session(execution_id: str) -> None:
    async with _BROWSER_SESSION_LOCK:
        expiry = _BROWSER_SESSION_EXPIRY.pop(execution_id, None)
        session = _BROWSER_SESSIONS.pop(execution_id, None)

    if expiry is not None and expiry is not asyncio.current_task():
        expiry.cancel()
        await asyncio.gather(expiry, return_exceptions=True)
    if session is None:
        return

    playwright, browser, _page = session
    try:
        await asyncio.wait_for(browser.close(), timeout=3)
    except Exception:
        pass
    try:
        await asyncio.wait_for(playwright.stop(), timeout=3)
    except Exception:
        pass


async def close_all_browser_sessions() -> None:
    async with _BROWSER_SESSION_LOCK:
        execution_ids = list(_BROWSER_SESSIONS)
    if execution_ids:
        await asyncio.gather(
            *(close_browser_session(execution_id) for execution_id in execution_ids),
            return_exceptions=True,
        )


async def _navigate_page(page: Any, url: str) -> None:
    """Retry one transient navigation failure, falling back to response commit."""
    for attempt in range(2):
        try:
            await page.goto(
                url,
                wait_until="domcontentloaded" if attempt == 0 else "commit",
                timeout=NAVIGATION_TIMEOUT_MS if attempt == 0 else 10_000,
            )
            return
        except Exception as exc:
            message = str(exc).lower()
            transient_network_errors = (
                "net::err_name_not_resolved",
                "net::err_connection_reset",
                "net::err_connection_closed",
                "net::err_timed_out",
                "net::err_network_changed",
                "net::err_internet_disconnected",
            )
            retryable = (
                "timeout" in message
                or any(error in message for error in transient_network_errors)
                or "temporarily" in message
            )
            if attempt == 0 and retryable:
                await asyncio.sleep(0.4)
                continue
            raise


class _PageTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr"} and not self._skip_depth:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in {"p", "div", "li", "h1", "h2", "h3", "h4", "tr"} and not self._skip_depth:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        value = " ".join(data.split())
        if value:
            self.parts.append(value)
            if self._in_title:
                self.title_parts.append(value)


class BrowserTool(Tool):
    name = "browser"
    description = (
        "Use a real Chromium browser to load JavaScript-rendered public webpages and extract readable content. "
        "Supports navigation, clicking, filling form fields, and screenshots. Every network request is checked "
        "against AgentForge's public-URL policy."
    )

    def __init__(self, http_tool=None):
        # Production uses Playwright. An injected adapter remains supported for
        # legacy callers and deterministic tests that supply their own transport.
        self._http_tool = http_tool

    async def execute(self, input: str, *, context: Any) -> str:
        """Legacy entry point: navigate to one URL and return rendered page text."""
        url = input.strip()
        if not url:
            raise ToolExecutionError("browser requires an absolute public HTTP(S) URL")
        if self._http_tool is not None:
            return await self._legacy_http_extract(url, context)
        return await self._operate(url=url, action="navigate", selector="", text="", context=context)

    async def _legacy_http_extract(self, url: str, context: Any) -> str:
        try:
            assert_public_url(url)
        except UnsafeURL as exc:
            raise ToolExecutionError(str(exc)) from exc
        response = await self._http_tool.execute(f"GET {url}", context=context)
        marker = "Body:\n"
        body = response.split(marker, 1)[1] if marker in response else response
        body = body.split("\ntruncated:", 1)[0].strip()
        parser = _PageTextParser()
        parser.feed(body)
        title = " ".join(parser.title_parts).strip() or "(no page title)"
        readable = " ".join(" ".join(parser.parts).split())
        if len(readable) > MAX_PAGE_TEXT_CHARS:
            readable = readable[:MAX_PAGE_TEXT_CHARS] + "…[page text truncated]"
        return f"Title: {title}\nURL: {url}\n\n{readable or 'No readable page text was found.'}"

    async def operate(
        self, *, url: str, action: str = "navigate", selector: str = "",
        text: str = "", context: Any,
    ) -> str:
        return await self._operate(url=url, action=action, selector=selector, text=text, context=context)

    async def _operate(self, *, url: str, action: str, selector: str, text: str, context: Any) -> str:
        url = url.strip()
        if action not in {"navigate", "click", "fill", "screenshot", "read"}:
            raise ToolExecutionError("Browser action must be navigate, click, fill, screenshot, or read.")
        if action == "navigate":
            try:
                assert_public_url(url)
            except UnsafeURL as exc:
                raise ToolExecutionError(str(exc)) from exc
        execution_id = str(getattr(context, "execution_id", "default"))
        if getattr(sys, "frozen", False):
            bundled_browsers = os.path.join(os.path.dirname(sys.executable), "browser-cache")
            if os.path.isdir(bundled_browsers):
                os.environ["PLAYWRIGHT_BROWSERS_PATH"] = bundled_browsers
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise ToolExecutionError(
                "Playwright is not installed in this runtime. Reinstall AgentForge with its bundled browser runtime."
            ) from exc

        async with _BROWSER_SESSION_LOCK:
            session = _BROWSER_SESSIONS.get(execution_id)
            if session is None:
                if len(_BROWSER_SESSIONS) >= MAX_BROWSER_SESSIONS:
                    raise ToolExecutionError(
                        f"AgentForge already has {MAX_BROWSER_SESSIONS} active browser sessions. "
                        "Close an existing run or wait for it to finish before starting another browser task."
                    )
                playwright = await async_playwright().start()
                browser = None
                try:
                    browser = await playwright.chromium.launch(headless=True)
                    page = await browser.new_page()
                    await page.route("**/*", self._guard_request)
                except BaseException:
                    if browser is not None:
                        try:
                            await browser.close()
                        except Exception:
                            pass
                    try:
                        await playwright.stop()
                    except Exception:
                        pass
                    raise
                _BROWSER_SESSIONS[execution_id] = (playwright, browser, page)
                session = (playwright, browser, page)
            self._schedule_session_expiry(execution_id)
        playwright, browser, page = session
        try:
            if action == "navigate":
                await _navigate_page(page, url)
                try:
                    await page.wait_for_load_state("networkidle", timeout=2_000)
                except Exception:
                    pass
            elif action == "click":
                if not selector:
                    raise ToolExecutionError("Browser click requires a CSS selector.")
                await page.locator(selector).first.click(timeout=5_000)
                await page.wait_for_load_state("domcontentloaded", timeout=5_000)
            elif action == "fill":
                if not selector:
                    raise ToolExecutionError("Browser fill requires a CSS selector.")
                await page.locator(selector).first.fill(text, timeout=5_000)
            elif action == "screenshot":
                if not url and page.url == "about:blank":
                    raise ToolExecutionError("Navigate to a page before taking a screenshot.")
                path = os.path.join(str(getattr(getattr(context, "workspace", None), "root", ".")), ".agentforge", "browser.png")
                os.makedirs(os.path.dirname(path), exist_ok=True)
                await page.screenshot(path=path, full_page=False, timeout=5_000)
                return "Screenshot saved to workspace path .agentforge/browser.png"
            title = await page.title()
            body = await page.locator("body").inner_text(timeout=5_000)
            body = " ".join(body.split())
            if len(body) > MAX_PAGE_TEXT_CHARS:
                body = body[:MAX_PAGE_TEXT_CHARS] + "…[page text truncated]"
            return f"Title: {title or '(no page title)'}\nURL: {page.url}\n\n{body or 'No readable page text was found.'}"
        except ToolExecutionError:
            raise
        except Exception as exc:
            raise ToolExecutionError(f"Playwright browser action '{action}' failed: {type(exc).__name__}: {str(exc)[:400]}") from exc

    def _schedule_session_expiry(self, execution_id: str) -> None:
        previous = _BROWSER_SESSION_EXPIRY.pop(execution_id, None)
        if previous:
            previous.cancel()
        _BROWSER_SESSION_EXPIRY[execution_id] = asyncio.create_task(
            self._expire_session(execution_id), name=f"agentforge-browser-expiry-{execution_id}"
        )

    async def _expire_session(self, execution_id: str) -> None:
        try:
            await asyncio.sleep(180)
            async with _BROWSER_SESSION_LOCK:
                session = _BROWSER_SESSIONS.pop(execution_id, None)
                _BROWSER_SESSION_EXPIRY.pop(execution_id, None)
            if session:
                playwright, browser, _page = session
                try:
                    await asyncio.wait_for(browser.close(), timeout=3)
                finally:
                    await asyncio.wait_for(playwright.stop(), timeout=3)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Session cleanup is best-effort; never break another tool call.
            pass

    @staticmethod
    async def _guard_request(route) -> None:
        request_url = route.request.url
        parsed = urlparse(request_url)
        if parsed.scheme not in {"http", "https"}:
            await route.abort()
            return
        try:
            assert_public_url(request_url)
        except UnsafeURL:
            await route.abort()
            return
        await route.continue_()
