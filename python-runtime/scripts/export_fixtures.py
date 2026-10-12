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
    def raise_if_cancelled(self):
        return None


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

    async def emit(event: EventDraft) -> None:
        drafts.append(event)

    await FakeRunner().run(
        request, graph=graph, emit=emit, cancel=_Cancel(), approvals=_Approvals(),
        memory=None, workspace=None, tools=None,
    )
    now = datetime.now(timezone.utc)
    events = [
        RunEvent(execution_id=execution_id, seq=seq, ts=now + timedelta(microseconds=seq),
                 **event.model_dump())
        for seq, event in enumerate(drafts, 1)
    ]
    issues = check_events(events, platform_events=False, complete=True)
    if issues:
        raise RuntimeError(f"{name} produced an invalid trace:\n" + "\n".join(issues))
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
