from app.core.runner import RunnerCore
from app.services.runner_factory import get_runner


def test_runner_core_is_default_application_runner(monkeypatch):
    monkeypatch.delenv("AGENTFORGE_RUNNER", raising=False)
    monkeypatch.setenv("AGENTFORGE_FAKE_LLM", "true")

    runner = get_runner()

    assert isinstance(runner, RunnerCore)


def test_fake_runner_requires_explicit_override(monkeypatch):
    monkeypatch.setenv("AGENTFORGE_RUNNER", "fake")

    from app.dev.fake_runner import FakeRunner

    assert isinstance(get_runner(), FakeRunner)
