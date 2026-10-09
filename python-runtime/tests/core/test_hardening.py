import pytest
from pydantic import ValidationError
from app.contracts.run import BudgetSpec
from app.core.budget import BudgetExceededError,BudgetTracker
from app.core.checkpoint import AgentFrame,ExecutionCheckpoint,InMemoryCheckpointStore
from app.core.evaluation import EvaluationCaseResult,EvaluationReport
from app.core.scheduler import ScheduledTask,TaskPlan,TaskStatus

def test_budget_reservations_prevent_concurrent_oversubscription():
    b=BudgetTracker(BudgetSpec(max_llm_calls=1,max_total_tokens=100,max_seconds=30))
    r=b.reserve_llm_call(estimated_tokens=10)
    with pytest.raises(BudgetExceededError):b.reserve_llm_call(estimated_tokens=10)
    b.record_llm_call(input_tokens=5,output_tokens=5,reservation=r)
    assert b.totals.llm_calls==1

def test_budget_reservation_can_be_released():
    b=BudgetTracker(BudgetSpec(max_llm_calls=1,max_total_tokens=100,max_seconds=30))
    r=b.reserve_llm_call(estimated_tokens=10);b.release_reservation(r)
    assert b.reserve_llm_call(estimated_tokens=10).reservation_id!=r.reservation_id

def test_scheduler_rejects_cycles():
    with pytest.raises(ValidationError):
        TaskPlan(tasks={"a":ScheduledTask(task_id="a",agent_id="x",instruction="A",dependencies=["b"]),
                        "b":ScheduledTask(task_id="b",agent_id="x",instruction="B",dependencies=["a"])})

def test_scheduler_waits_for_dependencies():
    p=TaskPlan(tasks={"a":ScheduledTask(task_id="a",agent_id="x",instruction="A"),
                      "b":ScheduledTask(task_id="b",agent_id="x",instruction="B"),
                      "m":ScheduledTask(task_id="m",agent_id="root",instruction="merge",dependencies=["a","b"])})
    assert p.refresh_ready()==["a","b"]
    t=p.claim_ready(1)[0];p.complete(t.task_id);assert p.refresh_ready()==[]
    t=p.claim_ready(1)[0];p.complete(t.task_id);assert p.refresh_ready()==["m"]

def test_failed_task_blocks_dependents():
    p=TaskPlan(tasks={"a":ScheduledTask(task_id="a",agent_id="x",instruction="A"),
                      "b":ScheduledTask(task_id="b",agent_id="x",instruction="B",dependencies=["a"])})
    p.refresh_ready();p.fail(p.claim_ready(1)[0].task_id,"network down")
    assert p.tasks["b"].status==TaskStatus.BLOCKED

@pytest.mark.asyncio
async def test_checkpoint_store_copies_snapshots():
    s=InMemoryCheckpointStore()
    c=ExecutionCheckpoint(execution_id="e",graph_fingerprint="g",status="running",
        frames=[AgentFrame(invocation_id="i",agent_id="root",task="original")])
    await s.save(c);loaded=await s.load("e");loaded.frames[0].task="mutated"
    assert (await s.load("e")).frames[0].task=="original"

def test_evaluation_report_aggregates_failure_categories():
    r=EvaluationReport([EvaluationCaseResult("ok",True,1,.01,20),
                        EvaluationCaseResult("bad",False,3,None,10,"timeout")])
    assert r.pass_rate==.5 and r.summary()["failure_categories"]=={"timeout":1}
    assert r.known_total_cost_usd is None
