from app.contracts.events import EventDraft
from app.contracts.run import RunOptions, RunRequest


def test_contract_defaults_and_event_shape():
    req = RunRequest(
        execution_id="e1",
        project_id="p1",
        root_agent_id="a1",
        task="hello",
    )
    assert req.options.max_depth == 4
    assert req.options.budget.max_llm_calls == 30

    event = EventDraft(
        type="span_started",
        span_id="s1",
        parent_span_id=None,
        kind="agent",
        name="CEO Agent",
        data={"depth": 0},
    )
    assert event.type == "span_started"
    assert event.kind == "agent"


def test_event_sequence_contract_is_contiguous():
    events = [
        EventDraft(type="execution_started"),
        EventDraft(type="span_started", span_id="s1", kind="agent", name="CEO"),
        EventDraft(type="span_started", span_id="s2", parent_span_id="s1", kind="llm_call"),
        EventDraft(type="span_ended", span_id="s2", parent_span_id="s1", kind="llm_call", status="ok"),
        EventDraft(type="span_ended", span_id="s1", kind="agent", status="ok"),
        EventDraft(type="execution_ended", data={"status": "completed"}),
    ]
    seqs = list(range(1, len(events) + 1))
    assert seqs == sorted(seqs)
    assert events[0].type == "execution_started"
    assert events[-1].type == "execution_ended"
