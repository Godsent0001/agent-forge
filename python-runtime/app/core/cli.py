"""CLI tool for running agent graphs offline with FakeLLM and printing event streams."""
import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from app.contracts.checks import check_events
from app.contracts.events import EventDraft, RunEvent
from app.contracts.graph import AgentGraph
from app.contracts.run import RunOptions, RunRequest
from app.core.llm.fake import FakeLLM
from app.core.runner import RunnerCore


class DummyCancelToken:
    @property
    def cancelled(self) -> bool:
        return False

    def raise_if_cancelled(self) -> None:
        pass


class DummyApprovalGate:
    async def check(self, *, tool: str, permissions: set, args_preview: str, span_id: str, force: bool = False, reason: str = "") -> bool:
        return True


class DummyWorkspace:
    def __init__(self, root: Path):
        self.root = root

    def resolve(self, rel: str) -> Path:
        return self.root / rel

    def new_path(self, name: str) -> Path:
        return self.root / name

    def relative(self, p: Path) -> str:
        return str(p.relative_to(self.root))

    def write_result(self, tool_call_id: str, content: str) -> Any:
        res_dir = self.root / ".results"
        res_dir.mkdir(parents=True, exist_ok=True)
        p = res_dir / f"{tool_call_id}.txt"
        p.write_text(content, encoding="utf-8")
        from app.contracts.tools import ArtifactRef
        return ArtifactRef(path=str(p.relative_to(self.root)))


class DummyToolFactory:
    def build(self, binding: Any) -> Any:
        from app.contracts.tools import Tool, ToolResult
        class DummyTool(Tool):
            kind = binding.kind
            default_description = "Dummy tool"
            async def run(self, args: Any, ctx: Any) -> ToolResult:
                return ToolResult(ok=True, content=f"Executed {binding.kind} with {args}")
        return DummyTool()


async def main_async():
    parser = argparse.ArgumentParser(description="AgentForge Core CLI runner")
    parser.add_argument("cmd", choices=["run"])
    parser.add_argument("--graph", required=True, help="Path to graph JSON fixture")
    parser.add_argument("--task", required=True, help="Task prompt")
    parser.add_argument("--fake", action="store_true", help="Use FakeLLM")
    args = parser.parse_args()

    graph_path = Path(args.graph)
    if not graph_path.is_file():
        print(f"Error: Graph file '{graph_path}' not found.", file=sys.stderr)
        sys.exit(1)

    graph_data = json.loads(graph_path.read_text(encoding="utf-8"))
    graph = AgentGraph(**graph_data)

    events: list[RunEvent] = []
    seq_counter = 0

    async def emit(draft: EventDraft) -> None:
        nonlocal seq_counter
        seq_counter += 1
        event = RunEvent(
            execution_id="exec_cli_1",
            seq=seq_counter,
            ts=draft.ts if hasattr(draft, "ts") and draft.ts else "2026-10-06T12:00:00Z",
            type=draft.type,
            span_id=draft.span_id,
            parent_span_id=draft.parent_span_id,
            kind=draft.kind,
            name=draft.name,
            status=draft.status,
            data=draft.data,
        )
        events.append(event)
        print(f"[{event.seq:02d}] {event.type} | kind={event.kind} name={event.name} status={event.status} data={event.data}")

    fake_llm = FakeLLM() if args.fake else None
    runner = RunnerCore(fake_llm=fake_llm)

    req = RunRequest(
        execution_id="exec_cli_1",
        project_id="proj_1",
        root_agent_id=graph.root_id,
        task=args.task,
        options=RunOptions(scenario="cli_scenario"),
    )

    ws_dir = Path("/tmp/agentforge_cli_ws")
    ws_dir.mkdir(parents=True, exist_ok=True)

    result = await runner.run(
        req=req,
        graph=graph,
        emit=emit,
        cancel=DummyCancelToken(),
        approvals=DummyApprovalGate(),
        workspace=DummyWorkspace(ws_dir),
        tools=DummyToolFactory(),
        memory=None,
        lessons=None,
        intents=None,
        run_history=None,
    )

    print("\n--- RUN RESULT ---")
    print(f"Status: {result.status}")
    print(f"Final Output: {result.final_output}")
    print(f"Totals: {result.totals}")

    # Verify event stream compliance
    errs = check_events(events)
    if errs:
        print(f"\n[WARNING] Event stream compliance check errors: {errs}", file=sys.stderr)
    else:
        print("\n[OK] Event stream C-2 compliance verified.")


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
