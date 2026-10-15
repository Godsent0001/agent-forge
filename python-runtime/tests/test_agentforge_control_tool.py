from app.tools.agentforge_control import AgentForgeControlInput, AgentForgeControlTool


def test_system_engineer_management_tool_exposes_project_actions():
    schema = AgentForgeControlInput.model_json_schema()

    assert AgentForgeControlTool.kind == "agentforge_control"
    assert "inspect_project" in schema["properties"]["operation"]["enum"]
    assert "create_agent" in schema["properties"]["operation"]["enum"]
    assert "update_agent" in schema["properties"]["operation"]["enum"]
    assert "create_custom_http_tool" in schema["properties"]["operation"]["enum"]
    assert "attach_child_agent" in schema["properties"]["operation"]["enum"]
    assert "save_skill" in schema["properties"]["operation"]["enum"]
    assert "verify_execution" in schema["properties"]["operation"]["enum"]


def test_system_engineer_management_tool_does_not_offer_deletion():
    operations = set(AgentForgeControlInput.model_json_schema()["properties"]["operation"]["enum"])

    assert "delete_agent" not in operations
    assert "delete_tool" not in operations
    assert "delete_project" not in operations
