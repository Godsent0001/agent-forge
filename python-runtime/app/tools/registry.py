"""
Maps a persisted Tool row (kind="web_search", config={...}) to a live
Tool instance the runtime can call .execute() on. This is the seam where
a user-configured tool (from the Tool Library UI) becomes an actual
callable object at execution time.

Organized in two groups: the original general-purpose tools (web search,
python, filesystem, http), and the Tier-1 production catalog (audio
through orchestration shelves — see app/tools/catalog.py for the
descriptions shown in the picker UI).
"""

from __future__ import annotations

from app.contracts.graph import ToolBinding
from app.contracts.tools import Tool as V2Tool
from app.infra.workspace import data_dir
from app.tools.adapter import LegacyToolAdapter
from app.tools.agentforge_control import AgentForgeControlTool
from app.tools.asset_cache import (
    AssetCacheStoreTool,
    CacheEngineTool,
    DependencyEngineTool,
    ProductionConfigTool,
    ProjectManagerTool,
)
from app.tools.audio import (
    AudioAlignmentTool,
    AudioMixerTool,
    AudioProcessingTool,
    VoiceGeneratorTool,
)
from app.tools.base import Tool
from app.tools.browser import BrowserTool
from app.tools.camera import CameraAnimationTool, CameraDirectorTool
from app.tools.character import (
    BodyPoseTool,
    CharacterAssetManagerTool,
    CharacterPerformanceTool,
    CharacterRigTool,
    EyeEngineTool,
    FacialExpressionTool,
    FacialPerformanceTool,
    GestureEngineTool,
    LipSyncTool,
)
from app.tools.composition import CompositionEngineTool, EffectsEngineTool
from app.tools.custom_http import CustomHttpTool
from app.tools.filesystem import FileSystemTool
from app.tools.graphics import (
    CaptionEngineTool,
    DataVisualizationTool,
    DebateGraphicsTool,
    EvidenceGraphicsTool,
    HeadlineCardTool,
    TypographyEngineTool,
    VisualAssetManagerTool,
)
from app.tools.http_request import HttpRequestTool
from app.tools.log_search import LogSearchTool
from app.tools.orchestrator import PipelineOrchestratorTool
from app.tools.python_environment import PythonEnvironmentTool
from app.tools.python_exec import PythonExecTool
from app.tools.python_project import PythonProjectTool
from app.tools.qc import (
    AudioQCTool,
    AutomatedPreviewQCTool,
    LipSyncQCTool,
    SceneQCTool,
    ScriptToVideoQCTool,
    VideoQCTool,
)
from app.tools.rendering import (
    FinalRendererTool,
    PreviewRendererTool,
    RenderQueueTool,
    RenderWorkerTool,
)
from app.tools.scene import (
    LightingEngineTool,
    SceneBuilderTool,
    SceneTemplateManagerTool,
)
from app.tools.shell import ShellTool
from app.tools.timeline import TimelineEngineTool, TransitionEngineTool
from app.tools.video_clips import ClipExtractorTool, ClipFinderTool, VideoTranscriptTool
from app.tools.video_source import VideoSourceTool
from app.tools.web_search import WebSearchTool

# kind -> zero-arg factory. Config-driven ones (paths mostly) are handled
# in the branches below build_tool() for clarity.
_SIMPLE_FACTORIES: dict[str, type[Tool]] = {
    # General-purpose
    "web_search": WebSearchTool,
    "browser": BrowserTool,
    "log_search": LogSearchTool,
    "shell": ShellTool,
    "python": PythonExecTool,
    "http_request": HttpRequestTool,
    "video_source": VideoSourceTool,
    # Audio
    "audio_processing": AudioProcessingTool,
    "audio_alignment": AudioAlignmentTool,
    "audio_mixer": AudioMixerTool,
    # Character
    "lip_sync": LipSyncTool,
    "eye_engine": EyeEngineTool,
    "facial_expression": FacialExpressionTool,
    "facial_performance": FacialPerformanceTool,
    "gesture_engine": GestureEngineTool,
    "body_pose": BodyPoseTool,
    "character_performance": CharacterPerformanceTool,
    "character_rig": CharacterRigTool,
    # Scene
    "scene_builder": SceneBuilderTool,
    "lighting_engine": LightingEngineTool,
    # Camera
    "camera_director": CameraDirectorTool,
    "camera_animation": CameraAnimationTool,
    # Graphics
    "evidence_graphics": EvidenceGraphicsTool,
    "data_visualization": DataVisualizationTool,
    "headline_card": HeadlineCardTool,
    "debate_graphics": DebateGraphicsTool,
    "caption_engine": CaptionEngineTool,
    "typography_engine": TypographyEngineTool,
    # Timeline
    "timeline_engine": TimelineEngineTool,
    "transition_engine": TransitionEngineTool,
    # Composition
    "composition_engine": CompositionEngineTool,
    "effects_engine": EffectsEngineTool,
    # Rendering
    "preview_renderer": PreviewRendererTool,
    "final_renderer": FinalRendererTool,
    "render_worker": RenderWorkerTool,
    # Asset & Cache
    "dependency_engine": DependencyEngineTool,
    # QC
    "audio_qc": AudioQCTool,
    "video_qc": VideoQCTool,
    "lip_sync_qc": LipSyncQCTool,
    "scene_qc": SceneQCTool,
    "script_to_video_qc": ScriptToVideoQCTool,
    "automated_preview_qc": AutomatedPreviewQCTool,
    # Orchestration
    "pipeline_orchestrator": PipelineOrchestratorTool,
}


def build_tool(kind: str, config: dict) -> Tool:
    if kind in _SIMPLE_FACTORIES:
        return _SIMPLE_FACTORIES[kind]()

    # Config-driven tools — take a directory/path from the Tool row's config.
    if kind == "file_system":
        return FileSystemTool(root_dir=config.get("root_dir", "./files"))
    if kind == "voice_generator":
        return VoiceGeneratorTool(voices_dir=config.get("voices_dir", "./assets/voices"))
    if kind == "character_asset_manager":
        return CharacterAssetManagerTool(characters_dir=config.get("characters_dir", "./assets/characters"))
    if kind == "scene_template_manager":
        return SceneTemplateManagerTool(templates_dir=config.get("templates_dir", "./assets/scene_templates"))
    if kind == "visual_asset_manager":
        return VisualAssetManagerTool(assets_dir=config.get("assets_dir", "./assets/visuals"))
    if kind == "render_queue":
        return RenderQueueTool(queue_path=config.get("queue_path", "./output/render_queue.json"))
    if kind == "cache_engine":
        return CacheEngineTool(cache_dir=config.get("cache_dir", "./cache"))
    if kind == "project_manager":
        return ProjectManagerTool(projects_root=config.get("projects_root", "./projects"))
    if kind == "asset_cache_store":
        return AssetCacheStoreTool(store_dir=config.get("store_dir", "./assets/shared"))
    if kind == "production_config":
        return ProductionConfigTool(config_path=config.get("config_path", "./production_config.json"))

    raise ValueError(f"Unknown tool kind: {kind}")


# v2 registry contract (D-08). Keep build_tool() above unchanged: the legacy
# engine calls it directly and must retain its historical behavior.
NATIVE_TOOLS: dict[str, type[V2Tool]] = {
    "agentforge_control": AgentForgeControlTool,
    "video_transcript": VideoTranscriptTool,
    "clip_finder": ClipFinderTool,
    "clip_extractor": ClipExtractorTool,
    "python": PythonProjectTool,
    "python_environment": PythonEnvironmentTool,
}


_CONFIG_DRIVEN_KINDS = frozenset({
    "file_system", "voice_generator", "character_asset_manager", "scene_template_manager",
    "visual_asset_manager", "render_queue", "cache_engine", "project_manager",
    "asset_cache_store", "production_config",
})


def known_tool_kinds() -> frozenset[str]:
    """Every tool kind the v2 factory can build (used to validate new Tool rows)."""
    from app.core.tools.workspace_capabilities import WorkspaceCapabilityToolFactory

    return frozenset(_SIMPLE_FACTORIES) | _CONFIG_DRIVEN_KINDS | frozenset(NATIVE_TOOLS) | {
        "custom_http", *WorkspaceCapabilityToolFactory._BUILTINS,
    }


class DefaultToolFactory:
    """Build a native v2 tool when available, otherwise adapt the legacy tool."""

    def build(self, binding: ToolBinding) -> V2Tool:
        if binding.kind == "custom_http":
            return CustomHttpTool(binding)
        native = NATIVE_TOOLS.get(binding.kind)
        if native is not None:
            tool = native()
            # The Runner hands this to the tool as ToolContext.config.
            tool.binding_config = dict(binding.config or {})
            return tool

        # Never let a persisted Tool.config choose arbitrary host directories.
        # Legacy execution still uses build_tool() unchanged; v2 uses fixed data roots.
        root = data_dir()
        safe_roots = {
            "file_system": {"root_dir": str(root / "files")},
            "voice_generator": {"voices_dir": str(root / "assets" / "voices")},
            "character_asset_manager": {"characters_dir": str(root / "assets" / "characters")},
            "scene_template_manager": {"templates_dir": str(root / "assets" / "scene_templates")},
            "visual_asset_manager": {"assets_dir": str(root / "assets" / "visuals")},
            "render_queue": {"queue_path": str(root / "queues" / "render_queue.json")},
            "cache_engine": {"cache_dir": str(root / "cache")},
            "project_manager": {"projects_root": str(root / "projects")},
            "asset_cache_store": {"store_dir": str(root / "assets" / "shared")},
            "production_config": {"config_path": str(root / "production_config.json")},
        }
        config = dict(binding.config or {})
        for key in (
            "root_dir", "voices_dir", "characters_dir", "templates_dir", "assets_dir",
            "queue_path", "cache_dir", "projects_root", "store_dir", "config_path",
        ):
            config.pop(key, None)
        config.update(safe_roots.get(binding.kind, {}))
        legacy = build_tool(binding.kind, config)
        return LegacyToolAdapter(legacy, binding)
