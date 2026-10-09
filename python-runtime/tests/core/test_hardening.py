import pytest
from pydantic import ValidationError
from app.contracts.run import BudgetSpec
from app.core.budget import BudgetExceededError,BudgetTracker
from app.core.checkpoint import AgentFrame,ExecutionCheckpoint,InMemoryCheckpointStore,SQLiteCheckpointStore
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

@pytest.mark.asyncio
async def test_sqlite_checkpoint_store_survives_store_recreation(tmp_path):
    path=tmp_path/"checkpoints.sqlite3"
    first=SQLiteCheckpointStore(path)
    checkpoint=ExecutionCheckpoint(execution_id="durable-e",graph_fingerprint="graph",status="suspended",
        frames=[AgentFrame(invocation_id="i-1",agent_id="root",task="resume me")])
    await first.save(checkpoint)
    second=SQLiteCheckpointStore(path)
    restored=await second.load("durable-e")
    assert restored is not None
    assert restored.status=="suspended"
    assert restored.frames[0].task=="resume me"
    await second.delete("durable-e")
    assert await first.load("durable-e") is None


def test_budget_snapshot_restores_cumulative_usage():
    spec = BudgetSpec(max_llm_calls=5, max_total_tokens=100, max_seconds=30)
    original = BudgetTracker(spec)
    original.record_llm_call(input_tokens=12, output_tokens=7, cost_usd=0.02)
    snapshot = original.snapshot()
    restored = BudgetTracker(spec)
    restored.restore(snapshot)
    assert restored.totals.llm_calls == 1
    assert restored.totals.input_tokens == 12
    assert restored.totals.output_tokens == 7
    assert restored.totals.cost_usd == pytest.approx(0.02)
    assert restored.elapsed_seconds >= snapshot["elapsed_seconds"]


def test_scheduler_claims_ready_tasks_by_priority_then_id():
    plan = TaskPlan(tasks={
        "low": ScheduledTask(task_id="low", agent_id="root", instruction="low", priority=1),
        "z-high": ScheduledTask(task_id="z-high", agent_id="root", instruction="high z", priority=9),
        "a-high": ScheduledTask(task_id="a-high", agent_id="root", instruction="high a", priority=9),
    })
    plan.refresh_ready()
    claimed = plan.claim_ready(2)
    assert [task.task_id for task in claimed] == ["a-high", "z-high"]
