import pytest
from datetime import datetime, timezone
from app.contracts.graph import AgentSpec
from app.core.memory.inmemory import InMemoryIntentStore
from app.core.prompt_builder import build_system_prompt
from app.core.tools.yield_time import YieldTimeTool, YieldTimeInput
from app.core.claim_check import ClaimCheckEnvelope, ClaimCheckSummary


def test_temporal_context_prompt_injection():
    spec = AgentSpec(id="a1", name="Agent", provider="fake", model="fake")
    temp_ctx = {
        "current_time_iso": "2026-10-09T01:02:32Z",
        "epoch_timestamp_ms": 1791507752000,
        "session_elapsed_ms": 3410,
        "remaining_budget_ms": 300000,
    }
    prompt = build_system_prompt(spec, temporal_context=temp_ctx)
    assert "_temporal_context" in prompt
    assert "2026-10-09T01:02:32Z" in prompt


@pytest.mark.asyncio
async def test_yield_time_short_wait():
    tool = YieldTimeTool()
    ctx = None
    res = await tool.run(YieldTimeInput(wake_at="0.01", reason="quick pause"), ctx)
    assert res.ok is True
    assert "In-process pause complete" in res.content


@pytest.mark.asyncio
async def test_yield_time_long_wait_hibernation():
    store = InMemoryIntentStore()
    tool = YieldTimeTool(intent_store=store)
    ctx = None
    res = await tool.run(YieldTimeInput(wake_at="300", reason="durable hibernation test"), ctx)
    assert res.ok is True
    assert "Durable hibernation scheduled" in res.content

    active_intents = await store.list("root", status="active")
    assert len(active_intents) == 1
    assert "durable hibernation test" in active_intents[0].text


def test_claim_check_temporal_telemetry():
    env = ClaimCheckEnvelope(
        task_id="t1",
        sender_id="p",
        recipient_id="c",
        status="COMPLETED",
        summary=ClaimCheckSummary(headline="Done"),
        result_artifact_uri="store://.results/t1.txt",
        _temporal_telemetry={
            "invoked_at_iso": "2026-10-09T01:02:00Z",
            "completed_at_iso": "2026-10-09T01:02:05Z",
            "duration_wall_clock_ms": 5000,
        },
    )
    json_str = env.model_dump_json(by_alias=True)
    assert "_temporal_telemetry" in json_str
    assert "5000" in json_str
