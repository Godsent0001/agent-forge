from app.core.llm.fake import FakeLLM
from app.core.runner import RunnerCore
from app.dev.fake_runner import FakeRunner
from app.services.runner_factory import get_runner


def test_runner_factory_defaults_to_fake(monkeypatch):
    monkeypatch.delenv("AGENTFORGE_RUNNER", raising=False)
    monkeypatch.delenv("AGENTFORGE_FAKE_LLM", raising=False)

    runner = get_runner()

    assert isinstance(runner, FakeRunner)


def test_runner_factory_builds_v2_with_offline_fake_llm(monkeypatch):
    monkeypatch.setenv("AGENTFORGE_RUNNER", "v2")
    monkeypatch.setenv("AGENTFORGE_FAKE_LLM", "1")

    runner = get_runner()

    assert isinstance(runner, RunnerCore)
    assert isinstance(runner.fake_llm, FakeLLM)


def test_runner_factory_builds_v2_with_real_llm_adapter_by_default(monkeypatch):
    monkeypatch.setenv("AGENTFORGE_RUNNER", "v2")
    monkeypatch.delenv("AGENTFORGE_FAKE_LLM", raising=False)

    runner = get_runner()

    assert isinstance(runner, RunnerCore)
    assert runner.fake_llm is None
