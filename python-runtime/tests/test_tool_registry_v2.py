import pytest
from pydantic import BaseModel

from app.contracts.graph import ToolBinding
from app.contracts.naming import dedupe_names, sanitize_tool_name
from app.contracts.tools import Tool as V2Tool
from app.contracts.tools import ToolContext, ToolError, ToolResult
from app.tools import registry
from app.tools.adapter import LegacyInput, LegacyToolAdapter
from app.tools.base import Tool as LegacyTool
from app.tools.base import ToolExecutionError


class _LegacyFails(LegacyTool):
    name = "failing_tool"
    description = "A legacy tool for adapter tests."

    async def execute(self, input: str, *, context):
        raise ToolExecutionError("expected legacy failure")


class _LegacyEcho(LegacyTool):
    name = "echo_tool"
    description = "Returns its input."

    async def execute(self, input: str, *, context):
        return input


class _NativeTool(V2Tool):
    kind = "web_search"
    default_description = "Native test tool."
    Input = LegacyInput

    async def run(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        return ToolResult(content=args.input)


def _binding(kind="python", name="python"):
    return ToolBinding(id="tool-id", kind=kind, name=name, config={})


@pytest.mark.asyncio
async def test_legacy_failure_is_converted_to_tool_error():
    adapter = LegacyToolAdapter(_LegacyFails(), _binding())
    with pytest.raises(ToolError, match="expected legacy failure"):
        await adapter.run(LegacyInput(input="test"), ctx=None)


@pytest.mark.asyncio
async def test_same_legacy_kind_can_have_distinct_tool_names():
    factory = registry.DefaultToolFactory()
    first = factory.build(_binding("http_request", "fetch_reference"))
    second = factory.build(_binding("http_request", "fetch_metadata"))
    assert first.name == "fetch_reference"
    assert second.name == "fetch_metadata"
    assert first is not second


def test_legacy_adapter_schema_is_a_single_input_string():
    assert LegacyInput.model_json_schema()["properties"]["input"]["type"] == "string"


def test_native_registry_entry_takes_precedence_over_legacy(monkeypatch):
    monkeypatch.setitem(registry.NATIVE_TOOLS, "web_search", _NativeTool)

    def fail_if_legacy_used(*args, **kwargs):
        raise AssertionError("legacy builder should not be called when a native tool exists")

    monkeypatch.setattr(registry, "build_tool", fail_if_legacy_used)
    built = registry.DefaultToolFactory().build(_binding("web_search", "search"))
    assert isinstance(built, _NativeTool)


def test_tool_name_sanitizing_contract():
    assert sanitize_tool_name("") == "tool"
    assert sanitize_tool_name("   ") == "tool"
    assert sanitize_tool_name("Web Search (new)") == "web_search__new_"
    assert sanitize_tool_name("café") == "caf_"
    assert sanitize_tool_name("2search") == "t_2search"
    assert len(sanitize_tool_name("a" * 100)) == 64
    assert dedupe_names(["x", "x", "x"]) == ["x", "x_2", "x_3"]
