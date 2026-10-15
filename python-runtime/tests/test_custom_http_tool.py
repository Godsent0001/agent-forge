from app.contracts.graph import ToolBinding
from app.tools.custom_http import CustomHttpTool


def _binding(method="POST"):
    return ToolBinding(
        id="tool-1",
        kind="custom_http",
        name="lookup_public_api",
        description="Look up a record in the public API.",
        config={
            "url": "https://api.example.com/lookup",
            "method": method,
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Record to look up"},
                    "limit": {"type": "integer", "description": "Maximum results"},
                },
                "required": ["query"],
            },
        },
    )


def test_custom_http_tool_exposes_configured_input_schema():
    tool = CustomHttpTool(_binding())

    schema = tool.Input.model_json_schema()

    assert tool.name == "lookup_public_api"
    assert schema["type"] == "object"
    assert "query" in schema["properties"]
    assert "limit" in schema["properties"]
    assert schema["required"] == ["query"]


def test_custom_http_tool_rejects_unsupported_methods():
    binding = _binding("DELETE")
    try:
        CustomHttpTool(binding)
    except ValueError as exc:
        assert "GET or POST" in str(exc)
    else:
        raise AssertionError("Unsupported HTTP methods must be rejected")


def test_custom_http_tool_rejects_non_http_urls():
    binding = _binding()
    binding.config["url"] = "file:///etc/passwd"
    try:
        CustomHttpTool(binding)
    except ValueError as exc:
        assert "absolute HTTP(S)" in str(exc)
    else:
        raise AssertionError("Non-HTTP URLs must be rejected")
