from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.contracts.tools import ToolError
from app.core.tools import web_capabilities


@pytest.mark.asyncio
async def test_web_search_uses_explicit_query_schema(monkeypatch):
    calls = []

    class FakeSearch:
        async def execute(self, value, *, context):
            calls.append((value, context))
            return "- Example (https://example.com): relevant"

    monkeypatch.setattr(web_capabilities, "LegacyWebSearchTool", FakeSearch)
    tool = web_capabilities.WebSearchCapability()
    context = SimpleNamespace()
    result = await tool.run(tool.Input(query="current power tank prices"), context)

    assert tool.Input.model_json_schema()["properties"].keys() == {"query"}
    assert calls == [("current power tank prices", context)]
    assert "https://example.com" in result.content


@pytest.mark.asyncio
async def test_browser_uses_explicit_url_schema(monkeypatch):
    calls = []

    class FakeBrowser:
        async def operate(self, *, url, action, selector, text, context):
            calls.append((url, action, selector, text, context))
            return "Status: 200\nTitle: Example"

    monkeypatch.setattr(web_capabilities, "LegacyBrowserTool", FakeBrowser)
    tool = web_capabilities.BrowserCapability()
    context = SimpleNamespace()
    result = await tool.run(tool.Input(url="https://example.com/docs"), context)

    assert set(tool.Input.model_json_schema()["properties"]) == {"url", "action", "selector", "text"}
    assert calls == [("https://example.com/docs", "navigate", "", "", context)]
    assert "Status: 200" in result.content


@pytest.mark.asyncio
async def test_web_capabilities_return_actionable_errors(monkeypatch):
    class BrokenSearch:
        async def execute(self, value, *, context):
            raise web_capabilities.ToolExecutionError("upstream unavailable")

    monkeypatch.setattr(web_capabilities, "LegacyWebSearchTool", BrokenSearch)
    tool = web_capabilities.WebSearchCapability()
    with pytest.raises(ToolError, match="upstream unavailable"):
        await tool.run(tool.Input(query="test"), SimpleNamespace())


def test_default_factory_registers_typed_web_tools():
    from app.contracts.graph import ToolBinding
    from app.tools.registry import DefaultToolFactory

    factory = DefaultToolFactory()
    search = factory.build(ToolBinding(id="search", kind="web_search", name="web_search"))
    browser = factory.build(ToolBinding(id="browser", kind="browser", name="browser"))

    assert isinstance(search, web_capabilities.WebSearchCapability)
    assert isinstance(browser, web_capabilities.BrowserCapability)
    assert "query" in search.Input.model_json_schema()["properties"]
    assert "url" in browser.Input.model_json_schema()["properties"]
