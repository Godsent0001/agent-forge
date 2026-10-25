from __future__ import annotations

from pathlib import Path

from app.contracts.tools import ArtifactRef
from app.infra.workspace import RunWorkspace as SafeRunWorkspace


class Workspace:
    def __init__(self, execution_id: str):
        self._workspace = SafeRunWorkspace(execution_id)
        self.root = self._workspace.root

    def resolve(self, rel: str) -> Path:
        return self._workspace.resolve(rel)

    def asset(self, rel: str) -> Path:
        """Resolve a reusable shared asset without exposing its host root."""
        return self._workspace.asset(rel)

    def new_path(self, name: str) -> Path:
        return self._workspace.new_path(name)

    def relative(self, p: Path) -> str:
        return self._workspace.relative(p)

    def write_result(self, tool_call_id: str, content: str) -> ArtifactRef:
        return self._workspace.write_result(tool_call_id, content)

    def cleanup(self) -> None:
        # Run artifacts must remain available to the UI after execution.
        return None
