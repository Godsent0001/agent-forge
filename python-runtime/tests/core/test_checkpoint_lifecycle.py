import asyncio
from datetime import datetime, timezone

from app.core.checkpoint import AgentFrame, ExecutionCheckpoint, SQLiteCheckpointStore


def test_checkpoint_preserves_interrupted_run_state(tmp_path):
    async def scenario():
        store = SQLiteCheckpointStore(tmp_path / ".agentforge" / "checkpoints.sqlite3")
        checkpoint = ExecutionCheckpoint(
            execution_id="exec-cancelled",
            graph_fingerprint="graph-hash",
            status="cancelled",
            frames=[
                AgentFrame(
                    invocation_id="invocation-1",
                    agent_id="agent-1",
                    task="Finish the report",
                    messages=[
                        {"role": "tool", "tool_call_id": "call-done", "content": "saved result"}
                    ],
                    pending_tool_call_ids=["call-in-flight"],
                    completed_tool_results={"call-done": "saved result"},
                )
            ],
            task_state={
                "messages": [
                    {"role": "tool", "tool_call_id": "call-done", "content": "saved result"}
                ],
                "pending_tool_call_ids": ["call-in-flight"],
                "completed_tool_results": {"call-done": "saved result"},
                "pending_reminder_ids": ["reminder-1"],
                "terminal_error": "Run was cancelled by user.",
            },
            metadata={"resume_semantics": "in-flight-tool-outcomes-are-not-replayed"},
            updated_at=datetime.now(timezone.utc),
        )
        await store.save(checkpoint)

        restored = await store.load("exec-cancelled")
        assert restored is not None
        assert restored.status == "cancelled"
        assert restored.task_state["pending_reminder_ids"] == ["reminder-1"]
        assert restored.task_state["completed_tool_results"]["call-done"] == "saved result"
        assert restored.task_state["pending_tool_call_ids"] == ["call-in-flight"]
        assert restored.frames[0].completed_tool_results["call-done"] == "saved result"

    asyncio.run(scenario())
