from __future__ import annotations

from app.contracts.run import RunRequest
from app.services.executions import _apply_project_defaults


def make_request() -> RunRequest:
    return RunRequest(
        execution_id="settings-test",
        project_id="project",
        root_agent_id="agent",
        task="Validate project defaults",
    )


def test_project_budget_and_parallel_defaults_are_applied():
    req = _apply_project_defaults(
        make_request(),
        {
            "budget": {
                "max_llm_calls": 7,
                "max_cost_usd": 0.12,
                "max_seconds": 45,
            },
        },
        parallel_execution=True,
    )
    assert req.options.parallel_tools is True
    assert req.options.budget.max_llm_calls == 7
    assert req.options.budget.max_cost_usd == 0.12
    assert req.options.budget.max_seconds == 45


def test_invalid_project_budget_values_do_not_disable_safety_limits():
    req = _apply_project_defaults(
        make_request(),
        {
            "budget": {
                "max_llm_calls": -1,
                "max_cost_usd": float("inf"),
                "max_seconds": 0,
            },
        },
        parallel_execution=False,
    )
    assert req.options.parallel_tools is False
    assert req.options.budget.max_llm_calls == 30
    assert req.options.budget.max_cost_usd == 0.5
    assert req.options.budget.max_seconds == 300


def test_project_can_explicitly_remove_cost_cap_but_keeps_other_limits():
    req = _apply_project_defaults(
        make_request(),
        {"budget": {"max_cost_usd": None, "max_llm_calls": 12}},
        parallel_execution=False,
    )
    assert req.options.budget.max_cost_usd is None
    assert req.options.budget.max_llm_calls == 12
    assert req.options.budget.max_seconds == 300
