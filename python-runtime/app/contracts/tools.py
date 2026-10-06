from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar, Literal, Protocol
from pydantic import BaseModel, Field


Permission = Literal["net", "fs_write", "subprocess"]


class ArtifactRef(BaseModel):
    path: str
    mime: str | None = None
    description: str | None = None


class ToolResult(BaseModel):
    ok: bool = True
    content: str
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    data: dict | None = None


class ToolError(Exception):
    """Expected tool failure visible to the model."""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class RunWorkspace(Protocol):
    root: Path

    def resolve(self, rel: str) -> Path: ...
    def new_path(self, name: str) -> Path: ...
    def relative(self, p: Path) -> str: ...


class ToolContext(Protocol):
    execution_id: str
    span_id: str
    workspace: RunWorkspace
    cancel: "CancelToken"
    config: dict


class Tool(ABC):
    kind: ClassVar[str]
    default_description: ClassVar[str]
    Input: ClassVar[type[BaseModel]]
    permissions: ClassVar[set[Permission]] = set()

    @abstractmethod
    async def run(self, args: BaseModel, ctx: ToolContext) -> ToolResult: ...
