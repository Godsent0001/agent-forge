"""C-3: tools (v2). Pure data and protocols (see docs/CONTRACTS.md)."""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar, Literal, Protocol

from pydantic import BaseModel

Permission = Literal["net", "fs_write", "subprocess"]

DEFAULT_MAX_RESULT_CHARS = 6_000     # what the model sees of one tool result, before the head+pointer rule
SAVE_RESULT_OVER_CHARS = 1_000       # results longer than this are also saved to .results/ (C-9)


class ArtifactRef(BaseModel):
    path: str                    # relative to the run workspace
    mime: str | None = None
    description: str | None = None


class ToolResult(BaseModel):
    ok: bool = True
    content: str                 # what the model sees (the Runner truncates it)
    artifacts: list[ArtifactRef] = []
    data: dict | None = None     # structured payload for the UI only
    truncated: bool = False      # the tool itself returned only part of the data
    next_offset: int | None = None   # where to continue when truncated (pagination convention, C-9)


class ToolError(Exception):
    """Expected failure (bad input, missing binary, denied...). The model sees the message."""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.message = message
        self.retryable = retryable


class CancelToken(Protocol):
    @property
    def cancelled(self) -> bool: ...
    def raise_if_cancelled(self) -> None: ...        # raises asyncio.CancelledError


class RunWorkspace(Protocol):
    root: Path                                   # <data_dir>/runs/<execution_id>/
    def resolve(self, rel: str) -> Path: ...     # raises ToolError on absolute paths, "..", symlink escapes
    def new_path(self, name: str) -> Path: ...   # safe, unique file path inside the workspace
    def relative(self, p: Path) -> str: ...
    def write_result(self, tool_call_id: str, content: str) -> ArtifactRef: ...
    # writes <root>/.results/<tool_call_id>.txt and returns its reference (used to save long tool results)


class ToolContext(Protocol):
    execution_id: str
    span_id: str
    workspace: RunWorkspace
    cancel: CancelToken
    config: dict                                 # ToolBinding.config


class Tool(ABC):
    kind: ClassVar[str]
    default_description: ClassVar[str]           # written FOR THE MODEL (see docs/TOOL-WRITING.md)
    Input: ClassVar[type[BaseModel]]             # the JSON Schema sent to the model comes from here
    permissions: ClassVar[set[Permission]] = set()

    @abstractmethod
    async def run(self, args: BaseModel, ctx: ToolContext) -> ToolResult: ...
