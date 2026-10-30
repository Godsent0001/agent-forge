from __future__ import annotations

from pathlib import Path

from app.contracts.tools import ArtifactRef
from app.infra.paths import project_dir
from app.infra.workspace import RunWorkspace as SafeRunWorkspace


class Workspace:
    def __init__(self, execution_id: str, project_id: str | None = None):
        # New executions use one visible, persistent workspace per project. Keep
        # the execution-scoped fallback for legacy callers and isolated tests.
        root = project_dir(project_id) / "workspace" if project_id else None
        self._workspace = SafeRunWorkspace(execution_id, root=root)
        self.root = self._workspace.root
        self.project_id = project_id

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
        # Project files and run artifacts must remain available after execution.
        return None
