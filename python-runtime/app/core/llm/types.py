"""LLM types and exceptions for AgentForge Core."""
from typing import Literal

from pydantic import BaseModel, Field


class TextPart(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ImagePart(BaseModel):
    type: Literal["image"] = "image"
    path: str
    mime: str


ContentPart = TextPart | ImagePart


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict = Field(default_factory=dict)


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict = Field(default_factory=dict)
    arguments_error: str | None = None


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


class LLMTurn(BaseModel):
    message: dict = Field(default_factory=dict)
    text: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    cost_usd: float | None = None
    finish_reason: str = "stop"
    model: str = ""
    reasoning_text: str | None = None


# ---- Exceptions ----

class LLMError(Exception):
    """Base exception for LLM adapter errors."""
    pass


class LLMAuthError(LLMError):
    """Authentication failed (401/403)."""
    pass


class LLMRateLimit(LLMError):
    """Rate limit exceeded (429)."""
    pass


class LLMTimeout(LLMError):
    """LLM call timed out."""
    pass


class LLMBadRequest(LLMError):
    """Bad request (400)."""
    pass


class LLMContextTooLong(LLMError):
    """Context window exceeded."""
    pass
