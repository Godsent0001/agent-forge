"""Adapter for legacy tools plus a centralized v2 workspace security boundary."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.contracts.graph import ToolBinding
from app.contracts.naming import sanitize_tool_name
from app.contracts.tools import (
    Permission,
    ToolContext,
    ToolError,
    ToolResult,
)
from app.contracts.tools import Tool as V2Tool
from app.infra.workspace import RunWorkspace as SafeRunWorkspace
from app.infra.workspace import data_dir
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
    "video_source": {"net"},
    "file_system": {"fs_write"},
    # These tools mutate shared, persistent state outside the disposable run workspace.
    # Require explicit user approval by default; project policy can still deny/allow them.
    "scene_template_manager": {"fs_write"},
    "render_queue": {"fs_write"},
    "project_manager": {"fs_write"},
    "asset_cache_store": {"fs_write"},
    "production_config": {"fs_write"},
    "cache_engine": {"fs_write"},
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
    "effects_engine": {"output_path": "effect_output.mp4"},
    "evidence_graphics": {"output_path": "evidence_card.png"},
    "data_visualization": {"output_path": "chart.png"},
    "headline_card": {"output_path": "headline_card.png"},
    "debate_graphics": {"output_path": "debate_label.png"},
    "caption_engine": {"output_path": "captions.srt"},
    "typography_engine": {"output_path": "typography.png"},
    "preview_renderer": {"output_path": "preview.mp4"},
    "final_renderer": {"output_path": "final.mp4"},
    "render_worker": {"output_path": "render.mp4"},
}
_OUTPUT_PATH_KEYS = {"output_path", "output_image_path", "output_video_path"}
_ID_KEYS = {"character_id", "episode_id", "job_id", "template_id", "voice"}


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


def _redact_host_paths(content: str, ctx: ToolContext) -> str:
    """Keep host filesystem roots out of tool results shown to the model or UI."""
    roots: set[Path] = {data_dir().resolve()}
    workspace_root = getattr(getattr(ctx, "workspace", None), "root", None)
    if workspace_root is not None:
        roots.add(Path(workspace_root).resolve())
    for root in sorted(roots, key=lambda item: len(str(item)), reverse=True):
        root_text = str(root)
        content = content.replace(root_text, ".")
        content = content.replace(root_text.replace("/", "\\"), ".")
    return content


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

    if kind == "asset_cache_store":
        for key in ("category", "name"):
            value = payload.get(key)
            if value not in (None, "") and (
                not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value)
            ):
                raise ToolError(f"Invalid {key}: use 1-64 letters, digits, underscore or hyphen")
    if kind == "visual_asset_manager" and payload.get("name") not in (None, ""):
        name = payload["name"]
        if not isinstance(name, str) or name in {".", ".."} or "/" in name or "\\" in name or "\x00" in name:
            raise ToolError("Visual asset name must be a filename, not a path")

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
        # The legacy loop reads .description; the v2 Runner reads default_description.
        self.description = self.default_description
        self.permissions = set(_PERMISSION_MAP.get(binding.kind, set()))

    async def execute(self, input: str, *, context: Any) -> str:
        """Safe compatibility facade for the legacy agent loop until S-04 removes it."""
        workspace = getattr(context, "workspace", None)
        if workspace is None:
            execution_id = getattr(context, "execution_id", None) or "legacy"
            workspace = SafeRunWorkspace(execution_id)
            setattr(context, "workspace", workspace)

        # These tools require the approval UI. The frozen legacy runner has no
        # compatible approval route, so it must not provide a bypass around /v2.
        if self.kind in {"python", "http_request"}:
            raise ToolExecutionError(
                f"{self.kind} is disabled in the legacy execution engine because it cannot "
                "present approval prompts; run this task through /v2/executions."
            )

        mutation_actions = {
            "scene_template_manager": ("get", {"save"}),
            "render_queue": ("list", {"enqueue", "update_status"}),
            "project_manager": ("scaffold", {"scaffold"}),
            "asset_cache_store": ("list", {"put"}),
            "production_config": ("get", {"set"}),
            "cache_engine": ("check", {"store"}),
        }
        if self.kind in mutation_actions:
            try:
                payload = json.loads(input)
            except (TypeError, json.JSONDecodeError):
                payload = {}
            if isinstance(payload, dict):
                default_action, blocked_actions = mutation_actions[self.kind]
                action = payload.get("action", default_action)
                if action in blocked_actions:
                    raise ToolExecutionError(
                        f"{self.kind}.{action} changes shared persistent state and requires approval; "
                        "that approval flow is available only through /v2/executions."
                    )

        try:
            normalized = _normalize_payload(self.kind, input, context)
            content = await self._legacy.execute(normalized, context=context)
            return _redact_host_paths(str(content), context)
        except Exception as exc:
            # Tool errors and OS exceptions often include host paths. Do not return those to the model.
            raise ToolExecutionError(_redact_host_paths(str(exc), context)) from exc

    async def run(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        try:
            normalized_input = _normalize_payload(self.kind, args.input, ctx)
            content = await self._legacy.execute(normalized_input, context=ctx)
        except ToolExecutionError as exc:
            # Expected tool errors can contain absolute shared-asset paths too.
            raise ToolError(_redact_host_paths(str(exc), ctx)) from exc
        content = _redact_host_paths(str(content), ctx)
        return ToolResult(content=content)
