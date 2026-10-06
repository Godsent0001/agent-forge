import asyncio
from uuid import uuid4

from app.contracts.events import EventDraft
from app.contracts.graph import AgentGraph
from app.contracts.runner import ApprovalGate, CancelToken, MemoryStore, ToolFactory
from app.contracts.run import RunRequest, RunResult, Totals
from app.contracts.tools import RunWorkspace


class FakeRunner:
    """Deterministic runner for platform development and lifecycle tests."""

    async def run(
        self,
        req: RunRequest,
        *,
        graph: AgentGraph,
        emit,
        cancel: CancelToken,
        approvals: ApprovalGate,
        memory: MemoryStore,
        workspace: RunWorkspace,
        tools: ToolFactory,
    ) -> RunResult:
        root = graph.agents[graph.root_id]
        span = str(uuid4())
        await emit(EventDraft(
            type="span_started",
            span_id=span,
            parent_span_id=None,
            kind="agent",
            name=root.name,
            data={"agent_id": root.id, "depth": 0, "input_preview": req.task[:500]},
        ))

        try:
            if req.options.scenario in {"sleep_3s", "slow"}:
                await asyncio.sleep(3)
            elif req.options.scenario == "tool_call":
                tool_span = str(uuid4())
                await emit(EventDraft(
                    type="span_started",
                    span_id=tool_span,
                    parent_span_id=span,
                    kind="tool_call",
                    name="fake_tool",
                    data={"tool_name": "fake_tool", "tool_call_id": "fake-1", "args": "{}"},
                ))
                await asyncio.sleep(0.05)
                await emit(EventDraft(
                    type="span_ended",
                    span_id=tool_span,
                    parent_span_id=span,
                    kind="tool_call",
                    status="ok",
                    data={"result_preview": "fake result", "is_error": False, "artifacts": []},
                ))
            else:
                await asyncio.sleep(0.01)

            cancel.raise_if_cancelled()
            return RunResult(
                status="completed",
                final_output=f"FakeRunner completed: {req.task}",
                totals=Totals(tool_calls=1 if req.options.scenario == "tool_call" else 0),
            )
        except asyncio.CancelledError:
            await emit(EventDraft(
                type="span_ended",
                span_id=span,
                parent_span_id=None,
                kind="agent",
                status="cancelled",
                data={"output_preview": ""},
            ))
            raise
        except Exception as exc:
            await emit(EventDraft(
                type="span_ended",
                span_id=span,
                parent_span_id=None,
                kind="agent",
                status="error",
                data={"output_preview": str(exc)},
            ))
            raise
        else:
            await emit(EventDraft(
                type="span_ended",
                span_id=span,
                parent_span_id=None,
                kind="agent",
                status="ok",
                data={"output_preview": "completed"},
            ))
