import os

from app.contracts.runner import Runner


def get_runner() -> Runner:
    mode = os.environ.get("AGENTFORGE_RUNNER", "fake").lower()
    if mode == "fake":
        from app.dev.fake_runner import FakeRunner
        return FakeRunner()
    raise RuntimeError(f"Unsupported AGENTFORGE_RUNNER={mode!r}; real runner is supplied by A-03")
