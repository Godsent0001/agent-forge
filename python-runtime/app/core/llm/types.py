"""LLM types and exceptions for AgentForge Core."""
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class TextPart(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ImagePart(BaseModel):
    type: Literal["image"] = "image"
    path: str
    mime: str


ContentPart = TextPart | ImagePart


class LLMParams(BaseModel):
    timeout_s: float = 60.0
    temperature: float | None = 0.2
    max_tokens: int | None = 4096


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def provider_safe_identifier(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
            raise ValueError("Tool identifier must contain 1-64 ASCII letters, digits, '_' or '-'.")
        return value


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
    cached: bool = False


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
