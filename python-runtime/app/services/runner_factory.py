import os

from app.contracts.runner import Runner


def get_runner() -> Runner:
    mode = os.environ.get("AGENTFORGE_RUNNER", "fake").lower()

    if mode == "fake":
        from app.dev.fake_runner import FakeRunner
        return FakeRunner()

    if mode == "v2":
        from app.core.runner import build_runner
        return build_runner()

    raise RuntimeError(f"Unsupported runner mode: {mode!r}; expected fake or v2")
