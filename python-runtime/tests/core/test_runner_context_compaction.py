from __future__ import annotations

from app.core.runner import _compact_old_tool_outputs


def test_old_tool_outputs_are_compacted_and_paths_preserved():
    messages = []
    for index in range(8):
        call_id = f"call-{index}"
        messages.append({
            "role": "assistant",
            "tool_calls": [{
                "id": call_id,
                "type": "function",
                "function": {"name": "shell", "arguments": "{}"},
            }],
        })
        messages.append({
            "role": "tool",
            "tool_call_id": call_id,
            "content": ("x" * 2500) + r" created C:\AgentForge\workspace\calculator\main.py " + ("y" * 1200),
        })

    compacted = _compact_old_tool_outputs(messages, keep_recent=6, max_chars=1800)
    tool_messages = [message for message in messages if message.get("role") == "tool"]

    assert compacted == 2
    assert "compacted to reduce repeated context" in tool_messages[0]["content"]
    assert r"C:\AgentForge\workspace\calculator\main.py" in tool_messages[0]["content"]
    assert len(tool_messages[0]["content"]) < 1800
    assert len(tool_messages[-1]["content"]) > 3000
