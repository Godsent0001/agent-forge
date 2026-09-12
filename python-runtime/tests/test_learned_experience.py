import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.db import Base
from app.llm import LLMInterface
from app.runtime.agent import RuntimeAgent
from app.runtime.context import ExecutionContext

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

@pytest.mark.asyncio
async def test_learned_experience_injection_and_update(db_session):
    # 1. Create project and agent in DB
    project = models.Project(name="Test Project")
    db_session.add(project)
    db_session.commit()

    agent_row = models.Agent(
        project_id=project.id,
        name="LearnedAgent",
        system_prompt="Test persona",
        learned_experience="I learned previously that step-by-step logic works best.",
        memory_enabled=False,
    )
    db_session.add(agent_row)
    db_session.commit()

    # 2. Mock LLM Interface
    mock_llm = MagicMock(spec=LLMInterface)
    mock_llm.reason = AsyncMock()
    mock_llm.synthesize_learned_experience = AsyncMock(
        return_value="I learned from executing this task that thorough validation prevents errors."
    )

    # First reason call returns final answer
    decision = MagicMock()
    decision.action = "final_answer"
    decision.answer = "Task complete successfully."
    mock_llm.reason.return_value = decision

    runtime_agent = RuntimeAgent(
        agent_row=agent_row,
        llm=mock_llm,
        tools={},
        db=db_session,
    )

    async def mock_sink(event):
        pass

    context = ExecutionContext(
        execution_id="exec_1",
        depth=0,
        visited_agent_ids=(agent_row.id,),
        sink=mock_sink,
    )

    # 3. Run Agent
    res = await runtime_agent.run("Execute test task", context=context)

    assert res == "Task complete successfully."

    # 4. Verify prompt layers sent to LLM reason call included learned experience
    reason_calls = mock_llm.reason.call_args_list
    assert len(reason_calls) > 0
    messages_sent = reason_calls[0][0][0]  # first arg of reason call is messages list

    learned_exp_prompt_layer = next(
        (m for m in messages_sent if m.startswith("[LEARNED EXPERIENCE & REFLECTION")), None
    )
    assert learned_exp_prompt_layer is not None
    assert "I learned previously that step-by-step logic works best." in learned_exp_prompt_layer

    # 5. Verify synthesize_learned_experience was called and DB updated
    mock_llm.synthesize_learned_experience.assert_called_once()
    synth_call_args = mock_llm.synthesize_learned_experience.call_args[1]
    assert synth_call_args["agent_name"] == "LearnedAgent"
    assert synth_call_args["existing_learned_experience"] == "I learned previously that step-by-step logic works best."
    assert synth_call_args["task_input"] == "Execute test task"
    assert synth_call_args["final_answer"] == "Task complete successfully."

    # Verify DB persistence
    updated_agent_row = db_session.get(models.Agent, agent_row.id)
    assert updated_agent_row.learned_experience == "I learned from executing this task that thorough validation prevents errors."
    assert runtime_agent.learned_experience == "I learned from executing this task that thorough validation prevents errors."
