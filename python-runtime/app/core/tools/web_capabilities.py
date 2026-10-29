"""Typed v2 adapters for web search and webpage reading.

The legacy tools accept one opaque string. The v2 Runner exposes task-specific
schemas so providers can reliably supply a query or URL instead of guessing a
generic `input` field.
"""
from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field

from app.contracts.tools import Permission, Tool, ToolContext, ToolError, ToolResult
from app.tools.base import ToolExecutionError
from app.tools.browser import BrowserTool as LegacyBrowserTool
from app.tools.web_search import WebSearchTool as LegacyWebSearchTool


class WebSearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=2000, description="Search query in natural language.")


class BrowserInput(BaseModel):
    url: str = Field(
        min_length=8,
        max_length=2048,
        description="Absolute public HTTP(S) URL to fetch and extract readable page text from.",
    )


class WebSearchCapability(Tool):
    kind: ClassVar[str] = "web_search"
    default_description: ClassVar[str] = (
        "Search the public web using free keyless search. Returns result titles, URLs, and snippets. "
        "Use the browser tool to read a result page."
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
        "Fetch a public HTTP(S) webpage and extract readable text. This is a page reader, "
        "not graphical browser automation; it does not click buttons or submit forms."
    )
    Input = BrowserInput
    permissions: set[Permission] = {"net"}

    def __init__(self) -> None:
        self._implementation = LegacyBrowserTool()

    async def run(self, args: BrowserInput, ctx: ToolContext) -> ToolResult:
        try:
            result = await self._implementation.execute(args.url, context=ctx)
        except ToolExecutionError as exc:
            raise ToolError(str(exc), retryable=True) from exc
        return ToolResult(content=result)
