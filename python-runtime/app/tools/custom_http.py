"""User-configured, schema-driven HTTP tools for RunnerCore.

Only GET and POST to public URLs are supported. The existing HTTP tool enforces
SSRF protections, redirect validation, response bounds, and request timeouts.
Credentials/custom headers are intentionally not accepted by this first version.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, create_model

from app.contracts.graph import ToolBinding
from app.contracts.tools import Tool, ToolContext, ToolResult
from app.tools.http_request import HttpRequestTool


_JSON_TYPES: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "object": dict,
    "array": list,
}


def _http_url(value: str):
    import httpx

    return httpx.URL(value)


def _merge_query(url: str, params: dict[str, str]) -> str:
    import httpx

    return str(httpx.URL(url).copy_merge_params(params))


def _input_model(schema: Any) -> type[BaseModel]:
    if not isinstance(schema, dict):
        raise ValueError("Custom HTTP input_schema must be a JSON Schema object")
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    if not isinstance(properties, dict) or not isinstance(required, list):
        raise ValueError("input_schema properties and required must be valid")
    fields: dict[str, tuple[Any, Any]] = {}
    for name, definition in properties.items():
        if not isinstance(name, str) or not name.isidentifier() or not isinstance(definition, dict):
            raise ValueError("Each input field needs a valid identifier and schema")
        field_type = _JSON_TYPES.get(definition.get("type", "string"))
        if field_type is None:
            raise ValueError(f"Unsupported custom HTTP field type for {name!r}")
        description = definition.get("description", "")
        default = ... if name in required else None
        fields[name] = (field_type | None if default is None else field_type, Field(default, description=description))
    if not fields:
        fields["payload"] = (dict, Field(default_factory=dict, description="JSON payload to send to the endpoint"))
    return create_model("CustomHttpToolInput", **fields)


class CustomHttpTool(Tool):
    """A user-defined API operation exposed with a model-visible JSON input schema."""

    kind = "custom_http"
    default_description = "Call the configured public HTTP endpoint with the declared JSON arguments."
    permissions = {"net"}

    def __init__(self, binding: ToolBinding):
        config = dict(binding.config or {})
        url = config.get("url")
        method = str(config.get("method", "POST")).upper()
        if not isinstance(url, str) or not url.strip():
            raise ValueError("Custom HTTP tool requires a URL")
        if method not in {"GET", "POST"}:
            raise ValueError("Custom HTTP tool method must be GET or POST")
        try:
            parsed = _http_url(url.strip())
        except Exception as exc:
            raise ValueError("Custom HTTP tool URL must be an absolute HTTP(S) URL") from exc
        if parsed.scheme not in {"http", "https"} or not parsed.host or parsed.username or parsed.password:
            raise ValueError("Custom HTTP tool URL must be an absolute HTTP(S) URL without embedded credentials")
        self.url = url.strip()
        self.method = method
        self.name = binding.name
        self.default_description = (binding.description or self.default_description)[:2000]
        self.Input = _input_model(config.get("input_schema", {}))

    async def run(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        payload = args.model_dump(exclude_none=True)
        if self.method == "GET":
            query_args = {
                key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
                for key, value in payload.items()
            }
            url = _merge_query(self.url, query_args)
            result = await HttpRequestTool().execute(f"GET {url}", context=ctx)
        else:
            result = await HttpRequestTool().execute(
                f"POST {self.url}::{json.dumps(payload, ensure_ascii=False)}",
                context=ctx,
            )
        return ToolResult(content=result)
