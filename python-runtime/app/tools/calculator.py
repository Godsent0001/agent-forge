"""Deterministic arithmetic tool with a structured, model-visible input schema."""
from __future__ import annotations

import json
import math
from decimal import Decimal, DecimalException
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, ValidationError, field_validator

from app.contracts.tools import Tool as V2Tool
from app.contracts.tools import ToolContext, ToolError, ToolResult
from app.tools.base import Tool as LegacyTool
from app.tools.base import ToolExecutionError

Operation = Literal["add", "subtract", "multiply", "divide"]

_SYMBOLS = {"add": "+", "subtract": "-", "multiply": "×", "divide": "÷"}


class CalculatorInput(BaseModel):
    """Arguments exposed to the LLM as JSON Schema; operands are numbers, not prose."""

    model_config = ConfigDict(extra="forbid")

    operation: Operation = Field(
        description="Arithmetic operation to perform: add, subtract, multiply, or divide."
    )
    a: StrictInt | StrictFloat = Field(description="First finite numeric operand.")
    b: StrictInt | StrictFloat = Field(description="Second finite numeric operand.")

    @field_validator("a", "b")
    @classmethod
    def require_finite_operand(cls, value: int | float) -> int | float:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Operands must be finite numbers.")
        return value


def _as_decimal(value: int | float | Decimal) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (DecimalException, ValueError) as exc:
        raise ValueError("Operands must be finite numbers.") from exc
    if not result.is_finite():
        raise ValueError("Operands must be finite numbers.")
    return result


def _calculate(operation: str, a: int | float | Decimal, b: int | float | Decimal) -> Decimal:
    """Compute without eval or an LLM-generated expression."""
    if operation not in _SYMBOLS:
        raise ValueError("Unsupported operation. Use add, subtract, multiply, or divide.")
    a = _as_decimal(a)
    b = _as_decimal(b)
    if operation == "divide" and b == 0:
        raise ValueError("Division by zero is not allowed.")
    try:
        if operation == "add":
            result = a + b
        elif operation == "subtract":
            result = a - b
        elif operation == "multiply":
            result = a * b
        else:
            result = a / b
    except DecimalException as exc:
        raise ValueError("The calculation exceeded the supported decimal range.") from exc
    if not result.is_finite():
        raise ValueError("The calculation did not produce a finite result.")
    return result


def _format_number(value: Decimal) -> str:
    if value == 0:
        return "0"
    rendered = format(value.normalize(), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def _result_payload(operation: str, a: Decimal, b: Decimal, result: Decimal) -> dict[str, str]:
    return {
        "operation": operation,
        "a": _format_number(a),
        "b": _format_number(b),
        "result": _format_number(result),
    }


def _result_content(payload: dict[str, str]) -> str:
    return (
        f"{payload['a']} {_SYMBOLS[payload['operation']]} "
        f"{payload['b']} = {payload['result']}"
    )


class CalculatorTool(V2Tool):
    """Native v2 calculator; the LLM receives numeric fields and an operation enum."""

    kind: ClassVar[str] = "calculator"
    default_description: ClassVar[str] = (
        "Perform deterministic arithmetic using the calculator rather than mental math. "
        "Supply operation (add, subtract, multiply, or divide) and numeric operands a and b. "
        "Returns the calculated result; division by zero is rejected."
    )
    Input: ClassVar[type[BaseModel]] = CalculatorInput
    permissions: ClassVar[set] = set()

    async def run(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        del ctx  # Arithmetic is pure and needs no workspace, network, or approval.
        values = CalculatorInput.model_validate(args.model_dump())
        try:
            result = _calculate(values.operation, values.a, values.b)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        payload = _result_payload(values.operation, values.a, values.b, result)
        return ToolResult(content=_result_content(payload), data=payload)


class LegacyCalculatorTool(LegacyTool):
    """Compatibility implementation for the legacy engine's string-input interface."""

    name = "calculator"
    description = CalculatorTool.default_description

    async def execute(self, input: str, *, context: Any) -> str:
        del context
        try:
            raw = json.loads(input)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ToolExecutionError(
                "Calculator input must be a JSON object with operation, a, and b."
            ) from exc
        if not isinstance(raw, dict):
            raise ToolExecutionError(
                "Calculator input must be a JSON object with operation, a, and b."
            )
        try:
            values = CalculatorInput.model_validate(raw)
            result = _calculate(values.operation, values.a, values.b)
        except ValidationError as exc:
            details = "; ".join(error["msg"] for error in exc.errors())
            raise ToolExecutionError(f"Invalid calculator arguments: {details}") from exc
        except ValueError as exc:
            raise ToolExecutionError(str(exc)) from exc
        return _result_content(_result_payload(values.operation, values.a, values.b, result))
