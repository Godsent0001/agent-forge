"""
The Tool Catalog: static metadata for every tool available to add to a
project's Tool Library, grouped into shelves (matching the 10-engine
grouping from the production toolkit spec).

This is separate from `models.Tool` (a project's actual configured tool
instances). The catalog is what the "Add Tool" picker in the UI browses;
picking an entry creates a `models.Tool` row with `kind` = the catalog id.

`status` is either:
  - "real": execute() does real work (ffmpeg/PIL/matplotlib/local logic/
    Piper TTS), no external paid API required.
  - "stub": the Tool class exists with the right name/description/
    input-output contract, but execute() raises a clear
    ToolExecutionError explaining exactly what's missing (currently only
    the Rive-based character rig renderer — see character.py).

Production IR (the shared scene-specification JSON shape every tool
reads/writes against) is NOT a catalog entry — it's not a callable tool,
it's the data contract. See app/tools/shared.py.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogEntry:
    kind: str
    name: str
    shelf: str
    description: str
    status: str  # "real" | "stub"


SHELVES: dict[str, str] = {
    "audio": "Audio",
    "character": "Character",
    "scene": "Scene",
    "camera": "Camera",
    "graphics": "Graphics",
    "timeline": "Timeline",
    "composition": "Composition",
    "rendering": "Rendering",
    "asset_cache": "Asset & Cache",
    "qc": "Quality Control",
    "orchestration": "Orchestration",
}


CATALOG: list[CatalogEntry] = [
    # --- Audio ---------------------------------------------------------
    CatalogEntry("voice_generator", "Voice Generator", "audio",
                 "Converts character dialogue into speech using Piper TTS "
                 "(local, offline, neural). Outputs a WAV file + duration metadata.",
                 "real"),
    CatalogEntry("audio_processing", "Audio Processing", "audio",
                 "Normalizes loudness, trims silence, and cleans up a generated "
                 "voice line via ffmpeg. Deterministic and fast.",
                 "real"),
    CatalogEntry("audio_alignment", "Audio Alignment", "audio",
                 "Produces word-level timing for a voice line from its transcript "
                 "and duration — feeds captions, lip-sync, and camera timing.",
                 "real"),
    CatalogEntry("audio_mixer", "Audio Mixer", "audio",
                 "Combines voice, music, and SFX tracks with volume automation, "
                 "ducking, and fades via ffmpeg.",
                 "real"),

    # --- Character -------------------------------------------------------
    CatalogEntry("lip_sync", "Lip-Sync Engine", "character",
                 "Converts word/phoneme timing into mouth-shape (viseme) "
                 "animation data. Approximate heuristic mapping, not a trained model.",
                 "real"),
    CatalogEntry("eye_engine", "Eye Engine", "character",
                 "Controls gaze direction, blinking, and focus targets, with "
                 "automatic natural blink/glance insertion.",
                 "real"),
    CatalogEntry("facial_expression", "Facial Expression Engine", "character",
                 "Produces continuous facial expression parameters (confidence, "
                 "anger, skepticism, smile) rather than discrete emotion switches.",
                 "real"),
    CatalogEntry("facial_performance", "Facial Performance Engine", "character",
                 "Combines dialogue text, emotion, and conversational context "
                 "into a facial behavior instruction (brow raise, tilt, etc).",
                 "real"),
    CatalogEntry("gesture_engine", "Gesture Engine", "character",
                 "Produces hand/arm gesture animation instructions (with "
                 "anticipation/hold/recovery phases) from a reusable gesture library.",
                 "real"),
    CatalogEntry("body_pose", "Body Pose Engine", "character",
                 "Controls a character's overall body stance and smooth "
                 "transitions between poses (lean forward, cross arms, etc).",
                 "real"),
    CatalogEntry("character_performance", "Character Performance Engine", "character",
                 "Combines lip-sync, face, eyes, gesture, and body into one "
                 "coherent per-character animation timeline.",
                 "real"),
    CatalogEntry("character_asset_manager", "Character Asset Manager", "character",
                 "Looks up and validates a character's reusable rig/voice/"
                 "texture assets within the project's asset store.",
                 "real"),
    CatalogEntry("character_rig", "Character Rig Engine", "character",
                 "Renders a character performance timeline into actual animated "
                 "frames via a Rive (.riv) vector rig. Needs a Rive asset + runtime.",
                 "stub"),

    # --- Scene -----------------------------------------------------------
    CatalogEntry("scene_template_manager", "Scene Template Manager", "scene",
                 "Manages reusable environment templates: background, lighting "
                 "preset, character positions, camera positions, prop/graphic zones.",
                 "real"),
    CatalogEntry("scene_builder", "Scene Builder", "scene",
                 "Assembles an actual scene from a production spec: character "
                 "placement, camera, evidence card position, caption zone.",
                 "real"),
    CatalogEntry("lighting_engine", "Lighting Engine", "scene",
                 "Selects a lighting mood preset (normal/dramatic/evidence/"
                 "tension/final) based on the moment in the script.",
                 "real"),

    # --- Camera ------------------------------------------------------------
    CatalogEntry("camera_director", "Camera Director", "camera",
                 "Automatically selects a shot type (two-shot, close-up, "
                 "evidence, split-screen) from the dialogue's semantic beat.",
                 "real"),
    CatalogEntry("camera_animation", "Camera Animation Engine", "camera",
                 "Produces the actual camera movement instructions: pan, push, "
                 "pull, tilt, tracking, focus, shake.",
                 "real"),

    # --- Graphics ----------------------------------------------------------
    CatalogEntry("visual_asset_manager", "Visual Asset Manager", "graphics",
                 "Manages non-character visual assets: logos, photos, icons, "
                 "maps, screenshots — loading, cropping, scaling, caching.",
                 "real"),
    CatalogEntry("evidence_graphics", "Evidence Graphics Engine", "graphics",
                 "Renders an evidence card image (stat + claim + source) as a PNG.",
                 "real"),
    CatalogEntry("data_visualization", "Data Visualization Engine", "graphics",
                 "Generates bar/line/comparison charts and animated counters "
                 "from structured data — deterministic, no AI model needed.",
                 "real"),
    CatalogEntry("headline_card", "Headline / News Card Engine", "graphics",
                 "Renders stylized BREAKING / REPORT / STUDY / COURT RULING cards.",
                 "real"),
    CatalogEntry("debate_graphics", "Debate Graphics Engine", "graphics",
                 "Renders franchise labels: CLAIM, COUNTER, EVIDENCE, REBUTTAL, "
                 "TRAP, CONCESSION, PERSPECTIVE FLIP, FINAL QUESTION.",
                 "real"),
    CatalogEntry("caption_engine", "Caption Engine", "graphics",
                 "Generates timed captions/subtitles (SRT + styling data) from "
                 "alignment output, with word-level emphasis support.",
                 "real"),
    CatalogEntry("typography_engine", "Typography Engine", "graphics",
                 "Renders large on-screen text elements (titles, big stat "
                 "callouts) with font hierarchy, spacing, and positioning.",
                 "real"),

    # --- Timeline ------------------------------------------------------
    CatalogEntry("timeline_engine", "Timeline Engine", "timeline",
                 "Core multi-track timeline (video/character/audio/caption/"
                 "graphics/camera/effects) with add/move/trim/split operations.",
                 "real"),
    CatalogEntry("transition_engine", "Transition Engine", "timeline",
                 "Defines transitions between shots: hard cut (default), zoom, "
                 "slide, graphic wipe, match transition.",
                 "real"),

    # --- Composition -----------------------------------------------------
    CatalogEntry("composition_engine", "Composition Engine", "composition",
                 "Layers background, characters, lighting, graphics, captions, "
                 "and effects into a single frame composition spec.",
                 "real"),
    CatalogEntry("effects_engine", "Effects Engine", "composition",
                 "Applies lightweight parameterized effects: blur, glow, shake, "
                 "vignette, motion blur, screen flash.",
                 "real"),

    # --- Rendering -----------------------------------------------------
    CatalogEntry("preview_renderer", "Preview Renderer", "rendering",
                 "Fast, low-resolution render (360p) for checking timing, "
                 "captions, camera, and lip-sync before a full render.",
                 "real"),
    CatalogEntry("final_renderer", "Final Renderer", "rendering",
                 "Produces the final deliverable: 1080x1920, 30fps, H.264/AAC.",
                 "real"),
    CatalogEntry("render_queue", "Render Queue", "rendering",
                 "Queues multiple episodes for rendering, tracks job status.",
                 "real"),
    CatalogEntry("render_worker", "Render Worker", "rendering",
                 "Executes a single queued render job end to end.",
                 "real"),

    # --- Asset & Cache -------------------------------------------------
    CatalogEntry("cache_engine", "Cache Engine", "asset_cache",
                 "Hashes tool inputs and skips regeneration when nothing "
                 "changed — audio, lip-sync, graphics, rendered scenes.",
                 "real"),
    CatalogEntry("dependency_engine", "Dependency Engine", "asset_cache",
                 "Tracks what needs regeneration when an upstream input "
                 "changes (dialogue edit -> voice -> lip-sync -> captions).",
                 "real"),
    CatalogEntry("project_manager", "Project Manager", "asset_cache",
                 "Scaffolds and manages a self-contained episode project "
                 "folder (audio/animation/graphics/assets/previews/renders).",
                 "real"),
    CatalogEntry("asset_cache_store", "Asset Cache", "asset_cache",
                 "Stores and looks up reusable franchise-wide assets (rigs, "
                 "fonts, music, SFX) so episodes don't duplicate them.",
                 "real"),
    CatalogEntry("production_config", "Production Configuration", "asset_cache",
                 "Centralizes render/audio/caption/character default settings "
                 "in one validated config, instead of hardcoded values.",
                 "real"),

    # --- QC ----------------------------------------------------------------
    CatalogEntry("audio_qc", "Audio QC", "qc",
                 "Checks generated audio for clipping, excessive silence, "
                 "abnormal volume, or corruption.",
                 "real"),
    CatalogEntry("video_qc", "Video QC", "qc",
                 "Checks final video for resolution, frame rate, black frames, "
                 "missing frames, and audio/video duration mismatch.",
                 "real"),
    CatalogEntry("lip_sync_qc", "Lip-Sync QC", "qc",
                 "Measures audio timing against mouth-shape timing and flags "
                 "sections with suspicious drift.",
                 "real"),
    CatalogEntry("scene_qc", "Scene QC", "qc",
                 "Checks a scene spec for off-screen characters, caption/"
                 "graphic collisions, and missing assets.",
                 "real"),
    CatalogEntry("script_to_video_qc", "Script-to-Video QC", "qc",
                 "Compares script, generated voice, and final video to catch "
                 "accidentally omitted lines.",
                 "real"),
    CatalogEntry("automated_preview_qc", "Automated Preview/QC", "qc",
                 "Runs a checklist against a preview render before committing "
                 "to an expensive final render.",
                 "real"),

    # --- Orchestration -------------------------------------------------
    CatalogEntry("pipeline_orchestrator", "Pipeline Orchestrator", "orchestration",
                 "Coordinates the full script-to-mp4 pipeline stage by stage: "
                 "voice -> alignment -> lip-sync -> performance -> graphics -> "
                 "camera -> timeline -> compositor -> render -> QC.",
                 "real"),
]


def get_catalog_entry(kind: str) -> CatalogEntry | None:
    return next((e for e in CATALOG if e.kind == kind), None)


def catalog_by_shelf() -> dict[str, list[CatalogEntry]]:
    grouped: dict[str, list[CatalogEntry]] = {shelf: [] for shelf in SHELVES}
    for entry in CATALOG:
        grouped.setdefault(entry.shelf, []).append(entry)
    return grouped
