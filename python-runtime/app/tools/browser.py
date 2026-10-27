"""Read and extract text from public web pages using the existing SSRF-safe HTTP tool."""
from __future__ import annotations

from html.parser import HTMLParser
from typing import Any

from app.tools.base import Tool, ToolExecutionError
from app.tools.http_request import HttpRequestTool

MAX_PAGE_TEXT_CHARS = 10_000


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
        if not value:
            return
        self.parts.append(value)
        if self._in_title:
            self.title_parts.append(value)


class BrowserTool(Tool):
    name = "browser"
    description = (
        "Open a public HTTP(S) webpage and return its title and readable text. "
        "Use web_search to discover URLs; this tool reads a page but does not click forms."
    )

    def __init__(self, http_tool: HttpRequestTool | None = None) -> None:
        self._http = http_tool or HttpRequestTool()

    async def execute(self, input: str, *, context: Any) -> str:
        url = input.strip()
        if not url:
            raise ToolExecutionError("browser requires an absolute public HTTP(S) URL")
        response = await self._http.execute(f"GET {url}", context=context)
        body_marker = "\nBody:\n"
        if body_marker in response:
            body = response.split(body_marker, 1)[1]
            body = body.rsplit("\ntruncated:", 1)[0]
        else:
            body = response
        parser = _PageTextParser()
        try:
            parser.feed(body)
        except Exception as exc:
            raise ToolExecutionError(f"could not parse page content: {exc}") from exc
        title = " ".join(" ".join(parser.title_parts).split()) or "(no page title)"
        text = " ".join(" ".join(parser.parts).split())
        if len(text) > MAX_PAGE_TEXT_CHARS:
            text = text[:MAX_PAGE_TEXT_CHARS] + "…[page text truncated]"
        if not text:
            text = "No readable page text was found."
        status = response.splitlines()[0] if response else "Status unavailable"
        return f"{status}\nTitle: {title}\nURL: {url}\n\n{text}"
