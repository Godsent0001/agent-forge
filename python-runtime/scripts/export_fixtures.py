"""Export contract-checked FakeRunner traces for frontend tests.

Run from python-runtime with: uv run python scripts/export_fixtures.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python-runtime"))

from app.contracts.checks import check_events  # noqa: E402
from app.contracts.events import EventDraft, RunEvent  # noqa: E402
from app.contracts.graph import AgentGraph, AgentSpec  # noqa: E402
from app.contracts.run import RunOptions, RunRequest  # noqa: E402
from app.dev.fake_runner import SCENARIO_NAMES, FakeRunner  # noqa: E402


class _Cancel:
    def __init__(self):
        self.cancelled = False

    def raise_if_cancelled(self):
        if self.cancelled:
            raise asyncio.CancelledError


class _Approvals:
    async def check(self, **kwargs):
        return True


async def export_one(name: str, target: Path) -> None:
    execution_id, root_id = str(uuid4()), str(uuid4())
    request = RunRequest(
        execution_id=execution_id, project_id=str(uuid4()), root_agent_id=root_id,
        task=f"fixture scenario: {name}", options=RunOptions(scenario=name),
    )
    graph = AgentGraph(root_id=root_id, agents={
        root_id: AgentSpec(id=root_id, name="Root Agent", provider="fake", model="fake/scenario"),
    })
    drafts: list[EventDraft] = []
    cancel = _Cancel()

    async def emit(event: EventDraft) -> None:
        drafts.append(event)

    task = asyncio.create_task(FakeRunner().run(
        request, graph=graph, emit=emit, cancel=cancel, approvals=_Approvals(),
        memory=None, workspace=None, tools=None,
    ))
    result = None
    terminal_status = "completed"
    try:
        if name == "long_running":
            await asyncio.sleep(1)
            cancel.cancelled = True
        result = await task
        terminal_status = result.status
    except asyncio.CancelledError:
        if name != "long_running":
            raise
        terminal_status = "cancelled"

    now = datetime.now(timezone.utc)
    span_events = [
        RunEvent(execution_id=execution_id, seq=seq, ts=now + timedelta(milliseconds=seq * 20),
                 **event.model_dump())
        for seq, event in enumerate(drafts, 1)
    ]
    issues = check_events(span_events, platform_events=False, complete=True)
    if issues:
        raise RuntimeError(f"{name} produced an invalid trace:\n" + "\n".join(issues))

    totals = result.totals.model_dump(mode="json") if result is not None else {}
    started = RunEvent(
        execution_id=execution_id, seq=1, ts=now, type="execution_started",
        data={"task": request.task},
    )
    ended = RunEvent(
        execution_id=execution_id, seq=len(span_events) + 2,
        ts=now + timedelta(milliseconds=(len(span_events) + 2) * 20),
        type="execution_ended",
        data={
            "status": terminal_status,
            "final_output": result.final_output if result is not None else None,
            "error": result.error if result is not None else None,
            "totals": totals,
        },
    )
    events = [started]
    for event in span_events:
        event.seq += 1
        events.append(event)
    events.append(ended)
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{name}.json").write_text(
        json.dumps([event.model_dump(mode="json") for event in events], indent=2) + "\n",
        encoding="utf-8",
    )


async def main() -> None:
    target = ROOT / "src" / "lib" / "__fixtures__"
    for name in SCENARIO_NAMES:
        await export_one(name, target)
        print(f"Exported {name}")


if __name__ == "__main__":
    asyncio.run(main())
