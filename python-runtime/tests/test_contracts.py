"""S-02: the contracts parse, the example trace is valid, and the checker catches each rule."""
import re
from datetime import datetime, timezone

from app.contracts import (AgentGraph, AgentSpec, MemoryOptions, RunOptions, RunRequest, RunResult,
                           ToolResult, dedupe_names, sanitize_tool_name, TOOL_NAME_RE)
from app.contracts.checks import check_events, example_events
from app.contracts.events import RunEvent


def _copy(e, **changes):
    d = e.model_dump()
    d.update(changes)
    return RunEvent(**d)


def _rules(problems):
    return {p.split(":")[0] for p in problems}


# ---- the example trace ---------------------------------------------------
def test_example_sequence_has_18_events_and_is_valid():
    events = example_events()
    assert len(events) == 18
    assert check_events(events) == []


def test_example_shape_matches_the_c2_table():
    ev = example_events()
    assert [e.type for e in ev][0] == "execution_started"
    assert [e.type for e in ev][-1] == "execution_ended"
    agents = [e for e in ev if e.type == "span_started" and e.kind == "agent"]
    assert [a.name for a in agents] == ["CEO Agent", "Research Agent"]
    assert agents[0].parent_span_id is None
    tool_research = next(e for e in ev if e.kind == "tool_call" and e.name == "research_agent")
    assert agents[1].parent_span_id == tool_research.span_id


def test_runner_only_stream_is_valid_without_platform_events():
    runner_events = [e for e in example_events() if e.type not in ("execution_started", "execution_ended")]
    renumbered = [_copy(e, seq=i) for i, e in enumerate(runner_events, 1)]
    assert check_events(renumbered, platform_events=False) == []


# ---- each rule is enforced ----------------------------------------------
def test_r1_unclosed_span_is_caught():
    ev = [e for e in example_events() if e.seq != 12]          # drop the span_ended of llm span s7
    ev = [_copy(e, seq=i) for i, e in enumerate(ev, 1)]
    assert "R1" in _rules(check_events(ev))


def test_r2_parent_ending_before_child_is_caught():
    ev = example_events()
    # swap events 13 and 14 (agent span s4 ends, then tool span s3 ends) with 12 and 13 order broken
    i_child, i_parent = 12, 13               # zero-based positions of seq 13 and seq 14
    ev[i_child], ev[i_parent] = ev[i_parent], ev[i_child]
    ev = [_copy(e, seq=i) for i, e in enumerate(ev, 1)]
    assert "R2" in _rules(check_events(ev))


def test_r3_seq_gap_is_caught():
    ev = example_events()
    ev[5] = _copy(ev[5], seq=99)
    assert "R3" in _rules(check_events(ev))


def test_r4_execution_events_must_bracket_the_stream():
    ev = example_events()
    assert "R4" in _rules(check_events(ev[1:]))                 # missing execution_started
    assert "R4" in _rules(check_events(ev[:-1]))                # missing execution_ended


def test_r5_untruncated_long_string_is_caught():
    ev = example_events()
    ev[1] = _copy(ev[1], data={**ev[1].data, "input_preview": "x" * 5000})
    assert "R5" in _rules(check_events(ev))


def test_r5_truncated_string_with_suffix_is_accepted():
    ev = example_events()
    ev[1] = _copy(ev[1], data={**ev[1].data, "input_preview": "x" * 2000 + "…[+3000 chars]"})
    assert check_events(ev) == []


def test_r6_non_uuid_span_id_is_caught():
    ev = example_events()
    ev[2] = _copy(ev[2], span_id="s2")
    assert "R6" in _rules(check_events(ev))


def test_a_tool_call_may_not_have_two_children():
    ev = example_events()
    extra = _copy(ev[5], seq=0, span_id="00000000-0000-4000-8000-0000000000aa")
    ev.insert(6, extra)
    ev = [_copy(e, seq=i) for i, e in enumerate(ev, 1)]
    assert "S4" in _rules(check_events(ev, complete=False))


# ---- models and defaults --------------------------------------------------
def test_run_request_minimal_and_defaults():
    r = RunRequest(execution_id="e1", project_id="p1", root_agent_id="a1", task="hi")
    assert r.history == [] and r.history_summary == "" and r.attachments == []
    assert r.options.budget.max_llm_calls == 30
    assert r.options.memory.episodic is True
    assert r.options.memory.intents is False
    assert r.options.memory.embedding_model is None
    assert r.options.memory.recall_budget_tokens == 800
    assert r.options.memory.max_items_per_agent == 500
    assert r.options.timezone == "UTC"
    assert r.options.llm_aliases == {}


def test_run_result_defaults():
    r = RunResult(status="completed")
    assert r.new_summary is None and r.summarized_count == 0
    assert r.totals.llm_calls == 0 and r.totals.cost_usd is None


def test_mutable_defaults_are_not_shared():
    a = RunRequest(execution_id="e1", project_id="p", root_agent_id="a", task="x")
    b = RunRequest(execution_id="e2", project_id="p", root_agent_id="a", task="y")
    a.history.append({"role": "user", "content": "hi"})
    a.options.llm_aliases["fast"] = "ollama/x"
    assert b.history == [] and b.options.llm_aliases == {}


def test_tool_result_pagination_fields():
    r = ToolResult(content="part 1", truncated=True, next_offset=200)
    assert r.truncated is True and r.next_offset == 200
    assert ToolResult(content="x").truncated is False


def test_agent_graph_builds():
    spec = AgentSpec(id="a1", name="CEO", provider="ollama", model="m")
    g = AgentGraph(root_id="a1", agents={"a1": spec})
    assert g.agents["a1"].params.reasoning == "off"
    assert g.agents["a1"].memory_enabled is False


# ---- naming ---------------------------------------------------------------
def test_sanitize_tool_name_always_matches_the_regex():
    for raw in ["Web Search", "web_search", "9lives", "", "Ünï-code!", "a" * 100, "  Mixed Case-ok  "]:
        name = sanitize_tool_name(raw)
        assert re.match(TOOL_NAME_RE, name), (raw, name)
    assert sanitize_tool_name("Web Search") == "web_search"
    assert sanitize_tool_name("9lives").startswith("t_")


def test_dedupe_names():
    assert dedupe_names(["x", "x", "x"]) == ["x", "x_2", "x_3"]
    assert dedupe_names(["x", "x_2", "x"]) == ["x", "x_2", "x_3"]
    assert dedupe_names(["a", "b"]) == ["a", "b"]
    out = dedupe_names(["a" * 64, "a" * 64])
    assert len(set(out)) == 2 and all(len(n) <= 64 for n in out)
