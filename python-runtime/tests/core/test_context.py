from pathlib import Path

from app.contracts.tools import ArtifactRef
from app.core.context import ContextCompiler


class Workspace:
    def __init__(self, root: Path):
        self.root = root

    def write_result(self, tool_call_id: str, content: str) -> ArtifactRef:
        directory = self.root / ".results"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{tool_call_id}.txt"
        path.write_text(content, encoding="utf-8")
        return ArtifactRef(path=str(path.relative_to(self.root)))


def test_context_compiler_compacts_old_tool_output_to_artifact_reference(tmp_path):
    workspace = Workspace(tmp_path)
    large_result = "pricing evidence " * 200
    messages = [
        {"role": "system", "content": "You are a research agent."},
        {"role": "user", "content": "Compare these prices."},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call-1", "type": "function", "function": {"name": "search", "arguments": "{}"}}
        ]},
        {"role": "tool", "tool_call_id": "call-1", "content": large_result},
        {"role": "assistant", "content": "I have the evidence."},
        {"role": "user", "content": "Now summarize it."},
    ]

    compiled, stats = ContextCompiler(max_context_chars=8_000, recent_tool_results=0).compile(messages, workspace)

    assert compiled is not messages
    assert messages[3]["content"] == large_result
    assert "Full result saved at .results/call-1.txt" in compiled[3]["content"]
    assert (tmp_path / ".results" / "call-1.txt").read_text(encoding="utf-8") == large_result
    assert compiled[2]["tool_calls"] == messages[2]["tool_calls"]
    assert compiled[-1]["content"] == "Now summarize it."
    assert stats.compacted_tool_results == 1
    assert stats.compiled_chars < stats.original_chars


def test_context_compiler_preserves_recent_tool_results(tmp_path):
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "task"},
        {"role": "tool", "tool_call_id": "old", "content": "x" * 1500},
        {"role": "tool", "tool_call_id": "recent", "content": "y" * 1500},
    ]
    compiled, stats = ContextCompiler(recent_tool_results=1).compile(messages, Workspace(tmp_path))
    assert "Full result saved at .results/old.txt" in compiled[2]["content"]
    assert compiled[3]["content"] == "y" * 1500
    assert stats.compacted_tool_results == 1


def test_context_compiler_does_not_overwrite_existing_full_artifact(tmp_path):
    workspace = Workspace(tmp_path)
    workspace.write_result("tool-1", "complete untruncated payload")
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "task"},
        {"role": "tool", "tool_call_id": "tool-1", "content": "x" * 1500},
    ]

    compiled, _ = ContextCompiler(recent_tool_results=0).compile(messages, workspace)

    assert "Full result saved at .results/tool-1.txt" in compiled[-1]["content"]
    assert (tmp_path / ".results" / "tool-1.txt").read_text(encoding="utf-8") == "complete untruncated payload"
