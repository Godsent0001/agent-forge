"""Episodic recall block builder and recall_run tool."""
from datetime import datetime, timedelta, timezone
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from app.contracts.memory import RunHistory
from app.contracts.tools import Tool, ToolResult


async def build_recent_runs_block(
    run_history: RunHistory,
    agent_id: str,
    now: datetime | None = None,
) -> str:
    """Build <recent_runs> block for root agent listing recent problem runs."""
    if not run_history:
        return ""

    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=48)

    try:
        problem_digests = await run_history.recent(
            agent_id=agent_id, since=since, limit=3, only_problems=True
        )
        if not problem_digests:
            return ""

        lines = []
        for d in problem_digests:
            dt_str = d.started_at.strftime("%Y-%m-%d %H:%M") if hasattr(d.started_at, "strftime") else str(d.started_at)
            err_str = f" -> error: {d.errors[0]}" if d.errors else ""
            lines.append(f"- {dt_str} \"{d.task_preview[:50]}\" -> {d.status}{err_str}")

        return "\n".join(lines)
    except Exception:
        return ""


class RecallRunInput(BaseModel):
    query: str = Field(description="Search query to find past execution runs")
    limit: int = Field(default=3, description="Maximum number of run digests to return")


class RecallRunTool(Tool):
    """Read-only tool to search past execution run digests."""

    kind: ClassVar[str] = "recall_run"
    default_description: ClassVar[str] = "Search past execution runs for error logs or outputs."
    Input: ClassVar[type[BaseModel]] = RecallRunInput

    def __init__(self, run_history: RunHistory):
        self.run_history = run_history

    async def run(self, args: RecallRunInput, ctx: Any) -> ToolResult:
        if not self.run_history:
            return ToolResult(ok=True, content="Run history unavailable.")

        digests = await self.run_history.search(
            agent_id=getattr(ctx, "agent_id", "root"), query=args.query, limit=args.limit
        )
        if not digests:
            return ToolResult(ok=True, content="No matching past runs found.")

        lines = ["<past_runs trust=\"untrusted\">"]
        for d in digests:
            lines.append(
                f"- Run {d.execution_id} [{d.status}]: Task=\"{d.task_preview}\" Output=\"{d.final_output_preview}\" Errors={d.errors}"
            )
        lines.append("</past_runs>")

        return ToolResult(ok=True, content="\n".join(lines))
