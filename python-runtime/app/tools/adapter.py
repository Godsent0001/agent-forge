"""Adapter for legacy tools plus a centralized v2 workspace security boundary."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.contracts.graph import ToolBinding
from app.contracts.naming import sanitize_tool_name
from app.contracts.tools import Permission, ToolContext, ToolError, ToolResult
from app.contracts.tools import Tool as V2Tool
from app.tools.base import Tool as LegacyTool
from app.tools.base import ToolExecutionError


class LegacyInput(BaseModel):
    """Legacy tools receive one explicit string, as documented in D-08."""
    model_config = ConfigDict(extra="forbid")
    input: str


_PERMISSION_MAP: dict[str, set[Permission]] = {
    "python": {"subprocess"},
    "http_request": {"net"},
    "web_search": {"net"},
    "file_system": {"fs_write"},
}

_INPUT_PATH_KEYS = {
    "audio_path", "voice_path", "music_path", "input_path", "image_path",
    "video_path", "preview_path", "src_path",
}
_OUTPUT_DEFAULTS = {
    "voice_generator": {"output_path": "voice.wav"},
    "audio_processing": {"output_path": "processed_voice.wav"},
    "audio_mixer": {"output_path": "mixed.wav"},
    "character_rig": {"output_image_path": "character_rig.png", "output_video_path": "character_rig.mp4"},
    "composition_engine": {"output_path": "composited_frame.png"},
    "effects_engine": {"output_path": "effected_frame.png"},
    "evidence_graphics": {"output_path": "evidence_card.png"},
    "data_visualization": {"output_path": "chart.png"},
    "headline_card": {"output_path": "headline_card.png"},
    "debate_graphics": {"output_path": "debate_label.png"},
    "caption_engine": {"output_path": "captions.srt"},
    "typography_engine": {"output_path": "typography.png"},
    "preview_renderer": {"output_path": "preview.mp4"},
    "final_renderer": {"output_path": "final.mp4"},
}
_OUTPUT_PATH_KEYS = {"output_path", "output_image_path", "output_video_path"}
_ID_KEYS = {"character_id", "episode_id", "job_id", "template_id"}


def _relative_input(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise ToolError("A relative workspace path is required")
    if raw.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", raw):
        raise ToolError("Absolute paths are not allowed for tool inputs")
    normalized = raw.replace("\\", "/")
    parts = normalized.split("/")
    if any(part == ".." for part in parts):
        raise ToolError("Parent-directory traversal is not allowed")
    if normalized.startswith("./output/"):
        normalized = normalized[len("./output/"): ]
    elif normalized.startswith("output/"):
        normalized = normalized[len("output/"): ]
    return normalized.removeprefix("./")


def _path_value(value: Any, ctx: ToolContext, *, output: bool = False) -> Any:
    if value is None or value == "":
        return value
    if not isinstance(value, str):
        raise ToolError("Tool path values must be strings")
    relative = _relative_input(value)
    try:
        resolved = ctx.workspace.resolve(relative)
    except Exception as exc:
        raise ToolError(f"Unsafe workspace path: {value}") from exc
    if output:
        resolved.parent.mkdir(parents=True, exist_ok=True)
    return str(resolved)


def _normalize_payload(kind: str, raw: str, ctx: ToolContext) -> str:
    """Resolve every recognized path argument under the run workspace."""
    # General-purpose tools have their own non-JSON input formats and guards.
    if kind in {"python", "http_request", "web_search", "file_system"}:
        return raw
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw
    if not isinstance(payload, dict):
        return raw

    for key in _ID_KEYS:
        value = payload.get(key)
        if value not in (None, ""):
            if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
                raise ToolError(f"Invalid {key}: use 1-64 letters, digits, underscore or hyphen")

    for key in _INPUT_PATH_KEYS:
        if key in payload and payload[key] not in (None, ""):
            payload[key] = _path_value(payload[key], ctx)

    if kind == "composition_engine":
        layers = payload.get("layers")
        if isinstance(layers, list):
            for layer in layers:
                if isinstance(layer, dict) and layer.get("image_path") not in (None, ""):
                    layer["image_path"] = _path_value(layer["image_path"], ctx)

    output_defaults = _OUTPUT_DEFAULTS.get(kind, {})
    for key, default in output_defaults.items():
        payload.setdefault(key, default)
    for key in _OUTPUT_PATH_KEYS:
        if key in payload and payload[key] not in (None, ""):
            payload[key] = _path_value(payload[key], ctx, output=True)

    return json.dumps(payload, ensure_ascii=False)


class LegacyToolAdapter(V2Tool):
    Input = LegacyInput

    def __init__(self, legacy: LegacyTool, binding: ToolBinding):
        self._legacy = legacy
        self.kind = binding.kind
        self.name = sanitize_tool_name(binding.name or binding.kind or legacy.name)
        self.default_description = binding.description or legacy.description
        self.permissions = set(_PERMISSION_MAP.get(binding.kind, set()))

    async def run(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        try:
            normalized_input = _normalize_payload(self.kind, args.input, ctx)
            content = await self._legacy.execute(normalized_input, context=ctx)
        except ToolExecutionError as exc:
            raise ToolError(str(exc)) from exc
        except ToolError:
            raise
        except Exception as exc:
            # Preserve unexpected errors for the core to report with its run trace.
            raise
        root = getattr(getattr(ctx, "workspace", None), "root", None)
        if root:
            root_text = str(Path(root).resolve())
            content = str(content).replace(root_text, ".")
            # Windows tools may serialize a backslash path even if workspace uses pathlib.
            content = content.replace(root_text.replace("/", "\\"), ".")
        return ToolResult(content=str(content))
