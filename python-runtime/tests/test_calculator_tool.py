import json

import pytest
from pydantic import ValidationError

from app.contracts.graph import ToolBinding
from app.contracts.tools import ToolError
from app.tools.calculator import CalculatorInput, CalculatorTool, LegacyCalculatorTool
from app.tools.catalog import get_catalog_entry
from app.tools.registry import DefaultToolFactory, build_tool


@pytest.mark.parametrize(
    ("operation", "a", "b", "expected"),
    [
        ("add", 1.25, 2.75, "1.25 + 2.75 = 4"),
        ("subtract", 7.2, 2.1, "7.2 - 2.1 = 5.1"),
        ("multiply", 1.2, 2.5, "1.2 × 2.5 = 3"),
        ("divide", 7.5, 2.5, "7.5 ÷ 2.5 = 3"),
    ],
)
@pytest.mark.asyncio
async def test_calculator_uses_deterministic_decimal_arithmetic(operation, a, b, expected):
    result = await CalculatorTool().run(
        CalculatorInput(operation=operation, a=a, b=b),
        ctx=None,
    )
    assert result.ok is True
    assert result.content == expected
    assert result.data["result"] == expected.rsplit(" = ", 1)[1]


def test_calculator_schema_exposes_structured_numeric_arguments():
    schema = CalculatorInput.model_json_schema()
    properties = schema["properties"]
    assert properties["a"]["type"] == "number"
    assert properties["b"]["type"] == "number"
    assert properties["operation"]["enum"] == ["add", "subtract", "multiply", "divide"]
    assert set(schema["required"]) == {"operation", "a", "b"}
    assert schema["additionalProperties"] is False


@pytest.mark.asyncio
async def test_division_by_zero_is_a_reportable_tool_error():
    with pytest.raises(ToolError, match="Division by zero"):
        await CalculatorTool().run(
            CalculatorInput(operation="divide", a=4, b=0),
            ctx=None,
        )


def test_invalid_operation_is_rejected_by_the_input_schema():
    with pytest.raises(ValidationError):
        CalculatorInput(operation="square_root", a=4, b=0)


def test_v2_factory_builds_native_calculator_with_numeric_schema():
    tool = DefaultToolFactory().build(
        ToolBinding(id="calculator-id", kind="calculator", name="calculator", config={})
    )
    assert isinstance(tool, CalculatorTool)
    assert tool.Input is CalculatorInput
    assert tool.Input.model_json_schema()["properties"]["a"]["type"] == "number"


@pytest.mark.asyncio
async def test_legacy_registry_remains_compatible():
    tool = build_tool("calculator", {})
    assert isinstance(tool, LegacyCalculatorTool)
    content = await tool.execute(
        json.dumps({"operation": "multiply", "a": 12, "b": 3}),
        context=None,
    )
    assert content == "12 × 3 = 36"


def test_calculator_is_listed_in_the_non_video_tool_catalog():
    entry = get_catalog_entry("calculator")
    assert entry is not None
    assert entry.shelf == "utilities"
    assert entry.pack is None
