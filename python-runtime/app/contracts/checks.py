"""Event-stream checker and the C-2 example sequence.

This is the one module in contracts/ that contains logic. It has no I/O, and it exists so
that the FakeRunner (D-05), the real Runner (A-03) and the tests all verify the same rules
R1 to R6 from docs/CONTRACTS.md.
"""
import json
import re
import uuid
from datetime import datetime, timedelta, timezone

from .events import EVENT_DATA_LIMIT_BYTES, EVENT_STRING_LIMIT, RunEvent

_TRUNC_SUFFIX = re.compile(r"…\[\+\d+ chars\]$")
_SUFFIX_ALLOWANCE = 24


def _is_uuid4(value) -> bool:
    try:
        u = uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return False
    return u.version == 4 and str(u) == str(value).lower()


def _long_strings(obj, path="data"):
    if isinstance(obj, str):
        if len(obj) > EVENT_STRING_LIMIT:
            if not _TRUNC_SUFFIX.search(obj) or len(obj) > EVENT_STRING_LIMIT + _SUFFIX_ALLOWANCE:
                yield path, len(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _long_strings(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from _long_strings(v, f"{path}[{i}]")


def check_events(events: list[RunEvent], *, platform_events: bool = True,
                 complete: bool = True) -> list[str]:
    """Return a list of rule violations (empty list = the stream is valid).

    platform_events=True : the stream includes execution_started / execution_ended (R4).
    platform_events=False: a Runner-only stream; execution_* events must not appear.
    complete=True        : the run is over, so every span must be closed (R1).
    """
    problems: list[str] = []
    started: dict[str, RunEvent] = {}
    ended: set[str] = set()
    children: dict[str, list[str]] = {}
    open_children: dict[str, int] = {}
    roots: list[str] = []

    for i, e in enumerate(events, 1):
        label = f"event #{i} ({e.type})"

        # R3: seq
        if e.seq != i:
            problems.append(f"R3: {label} has seq {e.seq}, expected {i}")

        # R5: truncation and size
        for path, n in _long_strings(e.data):
            problems.append(f"R5: {label} has a {n}-character string at {path} that is not truncated")
        try:
            size = len(json.dumps(e.data, default=str).encode("utf-8"))
        except (TypeError, ValueError):
            size = 0
            problems.append(f"R5: {label} data is not JSON-serializable")
        if size > EVENT_DATA_LIMIT_BYTES:
            problems.append(f"R5: {label} data is {size} bytes (limit {EVENT_DATA_LIMIT_BYTES})")

        if e.type == "span_started":
            sid = e.span_id
            if not _is_uuid4(sid):
                problems.append(f"R6: {label} span_id {sid!r} is not a uuid4 string")
            if e.kind is None:
                problems.append(f"{label}: span_started needs a kind")
            if sid in started:
                problems.append(f"R1: {label} reuses span_id {sid}")
                continue
            parent = e.parent_span_id
            if parent is None:
                roots.append(sid)
                if e.kind != "agent":
                    problems.append(f"S1: {label} root span must be kind 'agent', got {e.kind!r}")
            else:
                if not _is_uuid4(parent):
                    problems.append(f"R6: {label} parent_span_id {parent!r} is not a uuid4 string")
                if parent not in started:
                    problems.append(f"R2: {label} parent {parent} was never started")
                elif parent in ended:
                    problems.append(f"R2: {label} starts after its parent {parent} already ended")
                else:
                    pk = started[parent].kind
                    if e.kind in ("llm_call", "tool_call") and pk != "agent":
                        problems.append(f"S2: {label} ({e.kind}) must be a child of an agent span, not {pk!r}")
                    if e.kind == "agent" and pk != "tool_call":
                        problems.append(f"S3: {label} agent span must be a child of a tool_call, not {pk!r}")
                    if pk == "tool_call" and (e.kind != "agent" or children.get(parent)):
                        problems.append(f"S4: {label} a tool_call may have at most one child, and it must be an agent")
                children.setdefault(parent, []).append(sid)
                open_children[parent] = open_children.get(parent, 0) + 1
            started[sid] = e

        elif e.type == "span_ended":
            sid = e.span_id
            if sid not in started:
                problems.append(f"R1: {label} ends span {sid} that was never started")
                continue
            if sid in ended:
                problems.append(f"R1: {label} ends span {sid} twice")
                continue
            if e.status is None:
                problems.append(f"R1: {label} span_ended needs a status")
            if open_children.get(sid, 0) > 0:
                problems.append(f"R2: {label} ends span {sid} while {open_children[sid]} child span(s) are still open")
            ended.add(sid)
            parent = started[sid].parent_span_id
            if parent is not None:
                open_children[parent] = open_children.get(parent, 1) - 1

        elif e.type in ("execution_started", "execution_ended") and not platform_events:
            problems.append(f"R4: {label} must be emitted by the platform, not the Runner")

    # R1: every span closed
    if complete:
        for sid in started:
            if sid not in ended:
                problems.append(f"R1: span {sid} ({started[sid].kind}) was never ended")

    if len(roots) > 1:
        problems.append(f"S1: {len(roots)} root spans; a run has exactly one root agent span")

    # R4
    if platform_events and events:
        if events[0].type != "execution_started":
            problems.append("R4: the first event must be execution_started")
        if complete and events[-1].type != "execution_ended":
            problems.append("R4: the last event must be execution_ended")
        for i, e in enumerate(events, 1):
            if e.type == "execution_started" and i != 1:
                problems.append(f"R4: event #{i} execution_started must be first only")
            if e.type == "execution_ended" and i != len(events):
                problems.append(f"R4: event #{i} execution_ended must be last only")
    return problems


def example_events(execution_id: str = "11111111-1111-4111-8111-111111111111") -> list[RunEvent]:
    """The 18-event 'CEO delegates to Research, which searches the web' sequence from C-2."""
    s = [None] + [uuid.UUID(int=n, version=4) for n in range(1, 9)]   # s[1]..s[8]
    sid = lambda n: str(s[n])  # noqa: E731
    t0 = datetime(2026, 10, 6, 12, 0, 0, tzinfo=timezone.utc)
    usage = {"input_tokens": 120, "output_tokens": 30, "cache_read_tokens": 0, "cache_write_tokens": 0}

    def llm_end(n, calls):
        return dict(type="span_ended", span_id=sid(n), status="ok", data={
            "usage": usage, "cost_usd": 0.0, "finish_reason": "tool_calls" if calls else "stop",
            "tool_calls": calls})

    def llm_start(n, parent):
        return dict(type="span_started", span_id=sid(n), parent_span_id=sid(parent), kind="llm_call",
                    data={"provider": "ollama", "model": "example", "message_count": 3})

    spec = [
        dict(type="execution_started", data={"root_agent_id": "agent-ceo", "task_preview": "Find the latest news"}),
        dict(type="span_started", span_id=sid(1), parent_span_id=None, kind="agent", name="CEO Agent",
             data={"agent_id": "agent-ceo", "depth": 0, "input_preview": "Find the latest news"}),
        llm_start(2, 1),
        llm_end(2, ["research_agent"]),
        dict(type="span_started", span_id=sid(3), parent_span_id=sid(1), kind="tool_call", name="research_agent",
             data={"tool_name": "research_agent", "tool_call_id": "call_1", "args": '{"task": "news"}'}),
        dict(type="span_started", span_id=sid(4), parent_span_id=sid(3), kind="agent", name="Research Agent",
             data={"agent_id": "agent-research", "depth": 1, "input_preview": "news"}),
        llm_start(5, 4),
        llm_end(5, ["web_search"]),
        dict(type="span_started", span_id=sid(6), parent_span_id=sid(4), kind="tool_call", name="web_search",
             data={"tool_name": "web_search", "tool_call_id": "call_2", "args": '{"query": "news"}'}),
        dict(type="span_ended", span_id=sid(6), status="ok",
             data={"result_preview": "3 results", "is_error": False, "artifacts": []}),
        llm_start(7, 4),
        llm_end(7, []),
        dict(type="span_ended", span_id=sid(4), status="ok", data={"output_preview": "Here is the news"}),
        dict(type="span_ended", span_id=sid(3), status="ok",
             data={"result_preview": "Here is the news", "is_error": False, "artifacts": []}),
        llm_start(8, 1),
        llm_end(8, []),
        dict(type="span_ended", span_id=sid(1), status="ok", data={"output_preview": "Summary of the news"}),
        dict(type="execution_ended", data={"status": "completed", "final_output": "Summary of the news",
                                           "totals": {}, "error": None}),
    ]
    events = []
    for seq, d in enumerate(spec, 1):
        events.append(RunEvent(execution_id=execution_id, seq=seq, ts=t0 + timedelta(seconds=seq), **d))
    return events
