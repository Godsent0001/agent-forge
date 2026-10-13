from pathlib import Path
import tempfile

import pytest

from app.contracts.graph import AgentGraph, AgentSpec, ToolBinding
from app.contracts.run import RunRequest
from app.contracts.tools import Tool, ToolResult
from app.core.artifact_store import SQLiteArtifactStore
from app.core.execution_artifacts import ExecutionArtifactLifecycle
from app.core.durable_scheduler import SQLiteTaskPlanStore
from app.core.llm.fake import FakeLLM
from app.core.llm.types import LLMTurn, ToolCall
from app.core.runner import RunnerCore


class Workspace:
    def __init__(self, root: Path):
        self.root = root

    def resolve(self, rel: str) -> Path:
        path = Path(rel)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("unsafe path")
        target = (self.root / path).resolve()
        if not target.is_relative_to(self.root.resolve()):
            raise ValueError("path escaped workspace")
        return target

    def relative(self, path: Path) -> str:
        return str(path.relative_to(self.root))

    def write_result(self, tool_call_id: str, content: str):
        from app.contracts.tools import ArtifactRef
        target = self.root / ".results" / f"{tool_call_id}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return ArtifactRef(path=str(target.relative_to(self.root)))


class CancelToken:
    cancelled = False

    def raise_if_cancelled(self):
        return None


class ApprovalGate:
    async def check(self, **kwargs):
        return True


class ToolFactory:
    def build(self, binding):
        class SampleTool(Tool):
            kind = binding.kind
            default_description = "Test tool"

            async def run(self, args, ctx):
                return ToolResult(ok=True, content="durable tool result")

        return SampleTool()


@pytest.mark.asyncio
async def test_execution_artifact_lifecycle_persists_and_reports_unregistered_verifier(tmp_path):
    lifecycle = ExecutionArtifactLifecycle(tmp_path, "project-1")
    record, report = await lifecycle.persist(
        name="answer.txt",
        artifact_type="execution_output",
        content=b"final answer",
        media_type="text/plain",
        metadata={"execution_id": "run-1"},
    )

    assert record.project_id == "project-1"
    assert record.version == 1
    assert report.artifact_id == record.artifact_id
    assert report.status == "skipped"
    assert lifecycle.store.read(record.artifact_id).content == b"final answer"
    assert lifecycle.store.verify_integrity(record.artifact_id)


@pytest.mark.asyncio
async def test_runner_persists_tool_results_final_output_and_durable_task_plan(tmp_path):
    fake_llm = FakeLLM([
        LLMTurn(
            text="I will use the tool.",
            tool_calls=[ToolCall(id="call-1", name="sample", arguments={})],
        ),
        LLMTurn(text="Finished with a durable result."),
    ])
    runner = RunnerCore(fake_llm=fake_llm)
    workspace = Workspace(tmp_path)
    graph = AgentGraph(
        root_id="root",
        agents={
            "root": AgentSpec(
                id="root",
                name="Root",
                provider="fake",
                model="fake-model",
                tools=[ToolBinding(id="binding-1", kind="sample", name="sample")],
            )
        },
    )
    req = RunRequest(
        execution_id="execution-lifecycle-test",
        project_id="project-lifecycle-test",
        root_agent_id="root",
        task="Use the sample tool and finish.",
    )
    events = []

    async def emit(event):
        events.append(event)

    result = await runner.run(
        req=req,
        graph=graph,
        emit=emit,
        cancel=CancelToken(),
        approvals=ApprovalGate(),
        workspace=workspace,
        tools=ToolFactory(),
        memory=None,
        lessons=None,
        intents=None,
        run_history=None,
    )

    assert result.status == "completed"
    store = SQLiteArtifactStore(tmp_path)
    artifacts = store.list_project("project-lifecycle-test")
    assert {item.artifact_type for item in artifacts} >= {"tool_result", "execution_output"}
    assert any(event.type == "artifact_persisted" for event in events)
    assert any(event.type == "artifact_verification" for event in events)

    plan_store = SQLiteTaskPlanStore(tmp_path / ".agentforge" / "task_plans.sqlite3")
    plan_ids = plan_store.list_ids(limit=500)
    matching = [plan_store.get(plan_id) for plan_id in plan_ids if plan_id.startswith("execution-lifecycle-test:")]
    assert matching
    tasks = [task for plan in matching for task in plan.tasks.values()]
    assert any(task.status.value == "completed" and task.result_ref and task.result_ref.startswith("artifact://") for task in tasks)
