"""One canonical conversion from a v2 tool binding to an LLM tool spec."""
from __future__ import annotations

from app.contracts.graph import ToolBinding
from app.contracts.naming import sanitize_tool_name
from app.contracts.tools import Tool
from app.core.llm.types import ToolSpec


def tool_spec(binding: ToolBinding, tool: Tool, *, name: str | None = None) -> ToolSpec:
    """Build the model-visible schema from the exact tool Input contract."""
    input_model = getattr(tool, "Input", None)
    parameters = (
        input_model.model_json_schema()
        if input_model is not None and hasattr(input_model, "model_json_schema")
        else {}
    )
    return ToolSpec(
        name=sanitize_tool_name(name or binding.name),
        description=binding.description or tool.default_description,
        parameters=parameters,
    )
