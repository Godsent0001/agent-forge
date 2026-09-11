import pytest
from app.llm import LLMInterface, ToolSpec, LLMDecision

def test_messages_payload_building():
    llm = LLMInterface("anthropic", "claude-3-5-sonnet")
    messages = [
        "[SYSTEM PROMPT] You are a coding assistant.",
        "[AVAILABLE TOOLS AND SUB-AGENTS]\n- Tool 'python': Run python script",
        "[PARENT PROMPT] Write a fibonacci function",
    ]
    payload = llm._build_messages_payload(messages)
    assert len(payload) == 3
    assert payload[0]["role"] == "system"
    assert payload[1]["role"] == "system"
    assert payload[2]["role"] == "user"
