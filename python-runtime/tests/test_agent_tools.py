import pytest
from app.llm import LLMInterface

def test_messages_payload_building():
    llm = LLMInterface("anthropic", "claude-3-5-sonnet")
    messages = [
        "[SYSTEM PROMPT] You are a coding assistant.",
        "[TOOL-USE SCHEMA] Schema rules",
        "[AVAILABLE TOOLS AND SUB-AGENTS]\n- Tool 'python': Run python script",
        "[MEMORY CONTEXT - LOWER PRIORITY BACKGROUND HISTORICAL CONTEXT]\nOld task summary",
        "[CURRENT USER INSTRUCTION - CRITICAL HIGHEST PRIORITY]\nWrite a fibonacci function",
    ]
    payload = llm._build_messages_payload(messages)
    assert len(payload) == 5
    assert payload[0]["role"] == "system"
    assert payload[1]["role"] == "system"
    assert payload[2]["role"] == "system"
    assert payload[3]["role"] == "system"
    assert payload[4]["role"] == "user"
