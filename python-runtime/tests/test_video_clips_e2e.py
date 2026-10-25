"""End-to-end: ExecutionManager -> RunnerCore -> DefaultToolFactory -> clip_extractor.

Only the model is scripted. The tool registry, approvals, run workspace,
ffmpeg cut, artifact persistence and event stream are the production code.
"""
import json
import shutil
import subprocess
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from app import models
from app.contracts.run import RunRequest
from app.core.llm.fake import FakeLLM
from app.core.llm.types import LLMTurn, ToolCall
from app.core.runner import RunnerCore
from app.db import Base
from app.infra.workspace import RunWorkspace
from app.services import executions as executions_service
from app.services.executions import ExecutionManager
from tests.test_execution_v2 import wait_for_events, wait_for_terminal

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")


@pytest.mark.asyncio
async def test_agent_cuts_a_clip_from_an_attached_video(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTFORGE_DATA_DIR", str(tmp_path / "data"))
    engine = create_engine(
        f"sqlite:///file:clip_e2e_{uuid4().hex}?mode=memory&cache=shared&uri=true",
        connect_args={"check_same_thread": False}, poolclass=QueuePool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(executions_service, "SessionLocal", factory)

    db = factory()
    project = models.Project(name="clips")
    agent = models.Agent(project=project, name="Clipper", provider="anthropic", model="claude-sonnet-5-5")
    tool = models.Tool(project=project, name="Clip Extractor", kind="clip_extractor", config={"max_height": 360})
    db.add_all([project, agent, tool])
    db.flush()
    db.add(models.AgentToolLink(agent_id=agent.id, tool_id=tool.id))
    db.commit()
    project_id, agent_id = project.id, agent.id
    db.close()

    execution_id = str(uuid4())
    source = RunWorkspace(execution_id).resolve("attachments/talk.mp4")
    source.parent.mkdir(parents=True)
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=8",
        "-f", "lavfi", "-i", "sine=frequency=330:duration=8",
        "-c:v", "libx264", "-c:a", "aac", "-shortest", str(source),
    ], check=True)

    fake_llm = FakeLLM([
        LLMTurn(
            message={"role": "assistant", "content": None},
            tool_calls=[ToolCall(id="cut-1", name="clip_extractor", arguments={
                "source": "attachments/talk.mp4",
                "clips": [{"start": "0:02", "end": "0:05", "label": "Key moment"}],
            })],
        ),
        LLMTurn(message={"role": "assistant", "content": "Cut 1 clip."}, text="Cut 1 clip."),
    ])
    monkeypatch.setattr(executions_service, "get_runner", lambda: RunnerCore(fake_llm=fake_llm))

    ExecutionManager().start(RunRequest(
        execution_id=execution_id, project_id=project_id, root_agent_id=agent_id, task="Cut 0:02-0:05",
    ))
    row = await wait_for_terminal(factory, execution_id)
    assert row.status == "completed", row.error
    assert row.final_output == "Cut 1 clip."

    tool_message = next(m for m in fake_llm.received_calls[1]["messages"] if m.get("role") == "tool")
    result = json.loads(tool_message["content"])
    clip = RunWorkspace(execution_id).resolve(result["clips"][0]["file"])
    assert clip.name == "01-key-moment-2s.mp4" and clip.stat().st_size > 0

    events = await wait_for_events(factory, execution_id)
    persisted = [e.data for e in events if e.type == "artifact_persisted"]
    assert any(d.get("name") == "01-key-moment-2s.mp4" for d in persisted)
    approvals = factory().execute(
        select(models.ExecutionEventRow).where(models.ExecutionEventRow.type == "approval_requested")
    ).scalars().all()
    assert approvals == []  # default policy: clip_extractor runs without a prompt
    engine.dispose()
