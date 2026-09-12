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

from app.tools.asset_cache import (
    AssetCacheStoreTool, CacheEngineTool, DependencyEngineTool,
    ProductionConfigTool, ProjectManagerTool,
)
from app.tools.audio import AudioAlignmentTool, AudioMixerTool, AudioProcessingTool, VoiceGeneratorTool
from app.tools.base import Tool
from app.tools.camera import CameraAnimationTool, CameraDirectorTool
from app.tools.character import (
    BodyPoseTool, CharacterAssetManagerTool, CharacterDesignerTool, CharacterPerformanceTool,
    CharacterPreviewTool, CharacterRigTool, EyeEngineTool, FacialExpressionTool,
    FacialPerformanceTool, GestureEngineTool, LipSyncTool,
)
from app.tools.composition import CompositionEngineTool, EffectsEngineTool
from app.tools.filesystem import FileSystemTool
from app.tools.graphics import (
    CaptionEngineTool, DataVisualizationTool, DebateGraphicsTool, EvidenceGraphicsTool,
    HeadlineCardTool, PropDesignerTool, TypographyEngineTool, VisualAssetManagerTool,
)
from app.tools.scene import EnvironmentDesignerTool, LightingEngineTool, SceneBuilderTool, SceneTemplateManagerTool
from app.tools.http_request import HttpRequestTool
from app.tools.orchestrator import PipelineOrchestratorTool
from app.tools.python_exec import PythonExecTool
from app.tools.qc import (
    AudioQCTool, AutomatedPreviewQCTool, LipSyncQCTool, SceneQCTool,
    ScriptToVideoQCTool, VideoQCTool,
)
from app.tools.rendering import FinalRendererTool, PreviewRendererTool, RenderQueueTool, RenderWorkerTool
from app.tools.scene import LightingEngineTool, SceneBuilderTool, SceneTemplateManagerTool
from app.tools.timeline import TimelineEngineTool, TransitionEngineTool
from app.tools.web_search import WebSearchTool

# kind -> zero-arg factory. Config-driven ones (paths mostly) are handled
# in the branches below build_tool() for clarity.
_SIMPLE_FACTORIES: dict[str, type[Tool]] = {
    # General-purpose
    "web_search": WebSearchTool,
    "python": PythonExecTool,
    "http_request": HttpRequestTool,
    # Audio
    "audio_processing": AudioProcessingTool,
    "audio_alignment": AudioAlignmentTool,
    "audio_mixer": AudioMixerTool,
    # Character
    "character_designer": CharacterDesignerTool,
    "character_preview": CharacterPreviewTool,
    "lip_sync": LipSyncTool,
    "eye_engine": EyeEngineTool,
    "facial_expression": FacialExpressionTool,
    "facial_performance": FacialPerformanceTool,
    "gesture_engine": GestureEngineTool,
    "body_pose": BodyPoseTool,
    "character_performance": CharacterPerformanceTool,
    "character_rig": CharacterRigTool,
    # Scene
    "environment_designer": EnvironmentDesignerTool,
    "scene_builder": SceneBuilderTool,
    "lighting_engine": LightingEngineTool,
    # Graphics
    "prop_designer": PropDesignerTool,
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
    if kind == "character_designer":
        return CharacterDesignerTool(characters_dir=config.get("characters_dir", "./assets/characters"))
    if kind == "character_preview":
        return CharacterPreviewTool(characters_dir=config.get("characters_dir", "./assets/characters"))
    if kind == "character_asset_manager":
        return CharacterAssetManagerTool(characters_dir=config.get("characters_dir", "./assets/characters"))
    if kind == "environment_designer":
        return EnvironmentDesignerTool(environments_dir=config.get("environments_dir", "./assets/environments"))
    if kind == "prop_designer":
        return PropDesignerTool(props_dir=config.get("props_dir", "./assets/props"))
    if kind == "scene_template_manager":
        return SceneTemplateManagerTool(templates_dir=config.get("templates_dir", "./assets/scene_templates"))
    if kind == "visual_asset_manager":
        return VisualAssetManagerTool(assets_dir=config.get("assets_dir", "./assets"))
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
