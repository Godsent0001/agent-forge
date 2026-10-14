import os

from app.contracts.runner import Runner


def get_runner() -> Runner:
    mode = os.environ.get("AGENTFORGE_RUNNER", "fake").lower()

    if mode == "fake":
        from app.dev.fake_runner import FakeRunner
        return FakeRunner()

    if mode == "v2":
        from app.core.llm.fake import FakeLLM
        from app.core.runner import build_runner

        use_fake_llm = os.environ.get("AGENTFORGE_FAKE_LLM", "").lower() in {"1", "true", "yes", "on"}
        return build_runner(fake_llm=FakeLLM() if use_fake_llm else None)

    raise RuntimeError(f"Unsupported runner mode: {mode!r}; expected fake or v2")
