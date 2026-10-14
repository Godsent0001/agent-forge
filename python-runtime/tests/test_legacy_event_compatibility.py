from datetime import datetime, timezone

from app.contracts.events import RunEvent
from app.services.executions import legacy_event_payload


def test_runner_core_events_keep_legacy_payload_shape():
    event = RunEvent(
        execution_id="run-1",
        seq=1,
        ts=datetime.now(timezone.utc),
        type="span_started",
        kind="agent",
        name="Researcher",
        data={"depth": 2},
    )

    payload = legacy_event_payload(event)

    assert payload == {
        "type": "AgentStarted",
        "agent_name": "Researcher",
        "tool_name": None,
        "depth": 2,
        "data": {"depth": 2},
    }


def test_runner_core_terminal_event_exposes_legacy_final_field():
    event = RunEvent(
        execution_id="run-1",
        seq=2,
        ts=datetime.now(timezone.utc),
        type="execution_ended",
        data={"status": "completed", "final_output": "answer"},
    )

    payload = legacy_event_payload(event)

    assert payload["type"] == "ExecutionCompleted"
    assert payload["data"]["final"] == "answer"
