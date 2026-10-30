"""Typed v2 adapters for web search and webpage reading.

The legacy tools accept one opaque string. The v2 Runner exposes task-specific
schemas so providers can reliably supply a query or URL instead of guessing a
generic `input` field.
"""
from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, Field

from app.contracts.tools import Permission, Tool, ToolContext, ToolError, ToolResult
from app.tools.base import ToolExecutionError
from app.tools.browser import BrowserTool as LegacyBrowserTool
from app.tools.web_search import WebSearchTool as LegacyWebSearchTool


class WebSearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=2000, description="Search query in natural language.")


class BrowserInput(BaseModel):
    url: str = Field(
        default="",
        max_length=2048,
        description="Absolute public HTTP(S) URL for navigate; omit for actions on the current execution's browser page.",
    )
    action: Literal["navigate", "click", "fill", "screenshot", "read"] = Field(
        default="navigate",
        description="Browser operation: navigate to a URL, click a CSS selector, fill a selector, save a screenshot, or read the current page.",
    )
    selector: str = Field(default="", max_length=1000, description="CSS selector for click or fill.")
    text: str = Field(default="", max_length=10000, description="Text to enter for the fill action.")


class WebSearchCapability(Tool):
    kind: ClassVar[str] = "web_search"
    default_description: ClassVar[str] = (
        "Search the public web using Serper when configured, with a free DuckDuckGo fallback. "
        "Returns result titles, URLs, and snippets."
    )
    Input = WebSearchInput
    permissions: set[Permission] = {"net"}

    def __init__(self) -> None:
        self._implementation = LegacyWebSearchTool()

    async def run(self, args: WebSearchInput, ctx: ToolContext) -> ToolResult:
        try:
            result = await self._implementation.execute(args.query, context=ctx)
        except ToolExecutionError as exc:
            raise ToolError(str(exc), retryable=True) from exc
        return ToolResult(content=result)


class BrowserCapability(Tool):
    kind: ClassVar[str] = "browser"
    default_description: ClassVar[str] = (
        "Use a real Playwright Chromium browser to navigate JavaScript-rendered public pages, read text, "
        "click CSS selectors, fill fields, and save screenshots. Browser requests are checked against "
        "AgentForge's public-URL policy."
    )
    Input = BrowserInput
    permissions: set[Permission] = {"net"}

    def __init__(self) -> None:
        self._implementation = LegacyBrowserTool()

    async def run(self, args: BrowserInput, ctx: ToolContext) -> ToolResult:
        try:
            result = await self._implementation.operate(
                url=args.url, action=args.action, selector=args.selector, text=args.text, context=ctx
            )
        except ToolExecutionError as exc:
            raise ToolError(str(exc), retryable=True) from exc
        return ToolResult(content=result)
