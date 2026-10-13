"""Usage aggregation endpoint (D-21). Cost is null whenever pricing is unknown."""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import models
from app.deps import get_db

router = APIRouter(prefix="/v2/usage", tags=["usage"])


class UsageTotals(BaseModel):
    runs: int
    completed_runs: int
    failed_runs: int
    llm_calls: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float | None


class UsageBucket(BaseModel):
    date: str | None = None
    agent_id: str | None = None
    agent_name: str | None = None
    model: str | None = None
    runs: int
    llm_calls: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float | None


class UsageReport(BaseModel):
    project_id: str
    days: int
    totals: UsageTotals
    by_day: list[UsageBucket]
    by_agent: list[UsageBucket]
    by_model: list[UsageBucket]


def _number(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return 0
    return max(0, int(value))


def _cost(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        return None
    return float(value)


class _Accumulator:
    def __init__(self) -> None:
        self.runs = 0
        self.completed_runs = 0
        self.failed_runs = 0
        self.llm_calls = 0
        self.tool_calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.known_cost = 0.0
        self.unknown_cost = False

    def add(self, execution: models.Execution) -> None:
        self.runs += 1
        if execution.status == "completed":
            self.completed_runs += 1
        elif execution.status in {"error", "budget_exceeded", "cancelled", "interrupted"}:
            self.failed_runs += 1

        totals = execution.totals if isinstance(execution.totals, dict) else {}
        self.llm_calls += _number(totals.get("llm_calls"))
        self.tool_calls += _number(totals.get("tool_calls"))
        self.input_tokens += _number(totals.get("input_tokens"))
        self.output_tokens += _number(totals.get("output_tokens"))
        cost = _cost(totals.get("cost_usd"))
        if cost is None:
            self.unknown_cost = True
        else:
            self.known_cost += cost

    def to_totals(self) -> UsageTotals:
        return UsageTotals(
            runs=self.runs,
            completed_runs=self.completed_runs,
            failed_runs=self.failed_runs,
            llm_calls=self.llm_calls,
            tool_calls=self.tool_calls,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cost_usd=None if self.unknown_cost else round(self.known_cost, 6),
        )

    def to_bucket(self, **labels: Any) -> UsageBucket:
        totals = self.to_totals()
        return UsageBucket(
            **labels,
            runs=totals.runs,
            llm_calls=totals.llm_calls,
            tool_calls=totals.tool_calls,
            input_tokens=totals.input_tokens,
            output_tokens=totals.output_tokens,
            cost_usd=totals.cost_usd,
        )


@router.get("", response_model=UsageReport)
def get_usage(
    project_id: str,
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
) -> UsageReport:
    if db.get(models.Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # The ORM columns are timezone-naive for SQLite compatibility; use UTC naive cutoff.
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).replace(tzinfo=None)
    executions = (
        db.query(models.Execution)
        .filter(
            models.Execution.project_id == project_id,
            models.Execution.started_at >= cutoff,
        )
        .order_by(models.Execution.started_at.asc())
        .all()
    )

    total = _Accumulator()
    by_day: dict[str, _Accumulator] = defaultdict(_Accumulator)
    by_agent: dict[tuple[str | None, str], _Accumulator] = defaultdict(_Accumulator)
    by_model: dict[str, _Accumulator] = defaultdict(_Accumulator)
    agent_names: dict[tuple[str | None, str], str] = {}
    model_labels: dict[str, str] = {}

    for execution in executions:
        total.add(execution)
        day = execution.started_at.date().isoformat() if execution.started_at else "unknown"
        by_day[day].add(execution)

        snapshot = execution.agent_graph_snapshot if isinstance(execution.agent_graph_snapshot, dict) else {}
        agents = snapshot.get("agents") if isinstance(snapshot.get("agents"), dict) else {}
        root = agents.get(execution.root_agent_id) if execution.root_agent_id else None
        if not isinstance(root, dict):
            root = {}
        agent_id = execution.root_agent_id
        agent_name = str(root.get("name") or "Unknown agent")
        agent_key = (agent_id, agent_name)
        by_agent[agent_key].add(execution)
        agent_names[agent_key] = agent_name

        provider = str(root.get("provider") or "").strip()
        model_name = str(root.get("model") or "").strip()
        model_label = f"{provider}/{model_name}".strip("/") or "Unknown model"
        by_model[model_label].add(execution)
        model_labels[model_label] = model_label

    day_buckets = [
        by_day[day].to_bucket(date=day)
        for day in sorted(by_day)
    ]
    agent_buckets = [
        bucket.to_bucket(agent_id=agent_id, agent_name=agent_name)
        for (agent_id, agent_name), bucket in sorted(by_agent.items(), key=lambda item: (item[0][1].lower(), item[0][0] or ""))
    ]
    model_buckets = [
        by_model[label].to_bucket(model=label)
        for label in sorted(by_model, key=str.lower)
    ]

    return UsageReport(
        project_id=project_id,
        days=days,
        totals=total.to_totals(),
        by_day=day_buckets,
        by_agent=agent_buckets,
        by_model=model_buckets,
    )
