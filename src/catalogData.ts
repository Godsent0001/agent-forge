// Production Tool Catalog for AgentForge
export const SHELVES = {
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
  "video": "Video Sources"
} as const;

export const CATALOG = [
  {
    "kind": "voice_generator",
    "name": "Voice Generator",
    "shelf": "audio",
    "description": "Converts character dialogue into speech using Piper TTS (local, offline, neural). Outputs a WAV file + duration metadata.",
    "status": "real"
  },
  {
    "kind": "audio_processing",
    "name": "Audio Processing",
    "shelf": "audio",
    "description": "Normalizes loudness, trims silence, and cleans up a generated voice line via ffmpeg. Deterministic and fast.",
    "status": "real"
  },
  {
    "kind": "audio_alignment",
    "name": "Audio Alignment",
    "shelf": "audio",
    "description": "Produces word-level timing for a voice line from its transcript and duration \u2014 feeds captions, lip-sync, and camera timing.",
    "status": "real"
  },
  {
    "kind": "audio_mixer",
    "name": "Audio Mixer",
    "shelf": "audio",
    "description": "Combines voice, music, and SFX tracks with volume automation, ducking, and fades via ffmpeg.",
    "status": "real"
  },
  {
    "kind": "lip_sync",
    "name": "Lip-Sync Engine",
    "shelf": "character",
    "description": "Converts word/phoneme timing into mouth-shape (viseme) animation data. Approximate heuristic mapping, not a trained model.",
    "status": "real"
  },
  {
    "kind": "eye_engine",
    "name": "Eye Engine",
    "shelf": "character",
    "description": "Controls gaze direction, blinking, and focus targets, with automatic natural blink/glance insertion.",
    "status": "real"
  },
  {
    "kind": "facial_expression",
    "name": "Facial Expression Engine",
    "shelf": "character",
    "description": "Produces continuous facial expression parameters (confidence, anger, skepticism, smile) rather than discrete emotion switches.",
    "status": "real"
  },
  {
    "kind": "facial_performance",
    "name": "Facial Performance Engine",
    "shelf": "character",
    "description": "Combines dialogue text, emotion, and conversational context into a facial behavior instruction (brow raise, tilt, etc).",
    "status": "real"
  },
  {
    "kind": "gesture_engine",
    "name": "Gesture Engine",
    "shelf": "character",
    "description": "Produces hand/arm gesture animation instructions (with anticipation/hold/recovery phases) from a reusable gesture library.",
    "status": "real"
  },
  {
    "kind": "body_pose",
    "name": "Body Pose Engine",
    "shelf": "character",
    "description": "Controls a character's overall body stance and smooth transitions between poses (lean forward, cross arms, etc).",
    "status": "real"
  },
  {
    "kind": "character_performance",
    "name": "Character Performance Engine",
    "shelf": "character",
    "description": "Combines lip-sync, face, eyes, gesture, and body into one coherent per-character animation timeline.",
    "status": "real"
  },
  {
    "kind": "character_asset_manager",
    "name": "Character Asset Manager",
    "shelf": "character",
    "description": "Looks up and validates a character's reusable rig/voice/texture assets within the project's asset store.",
    "status": "real"
  },
  {
    "kind": "character_rig",
    "name": "Character Rig Engine",
    "shelf": "character",
    "description": "Renders a character performance timeline into actual animated frames via a Rive (.riv) vector rig. Needs a Rive asset + runtime.",
    "status": "stub"
  },
  {
    "kind": "scene_template_manager",
    "name": "Scene Template Manager",
    "shelf": "scene",
    "description": "Manages reusable environment templates: background, lighting preset, character positions, camera positions, prop/graphic zones.",
    "status": "real"
  },
  {
    "kind": "scene_builder",
    "name": "Scene Builder",
    "shelf": "scene",
    "description": "Assembles an actual scene from a production spec: character placement, camera, evidence card position, caption zone.",
    "status": "real"
  },
  {
    "kind": "lighting_engine",
    "name": "Lighting Engine",
    "shelf": "scene",
    "description": "Selects a lighting mood preset (normal/dramatic/evidence/tension/final) based on the moment in the script.",
    "status": "real"
  },
  {
    "kind": "camera_director",
    "name": "Camera Director",
    "shelf": "camera",
    "description": "Automatically selects a shot type (two-shot, close-up, evidence, split-screen) from the dialogue's semantic beat.",
    "status": "real"
  },
  {
    "kind": "camera_animation",
    "name": "Camera Animation Engine",
    "shelf": "camera",
    "description": "Produces the actual camera movement instructions: pan, push, pull, tilt, tracking, focus, shake.",
    "status": "real"
  },
  {
    "kind": "visual_asset_manager",
    "name": "Visual Asset Manager",
    "shelf": "graphics",
    "description": "Manages non-character visual assets: logos, photos, icons, maps, screenshots \u2014 loading, cropping, scaling, caching.",
    "status": "real"
  },
  {
    "kind": "evidence_graphics",
    "name": "Evidence Graphics Engine",
    "shelf": "graphics",
    "description": "Renders an evidence card image (stat + claim + source) as a PNG.",
    "status": "real"
  },
  {
    "kind": "data_visualization",
    "name": "Data Visualization Engine",
    "shelf": "graphics",
    "description": "Generates bar/line/comparison charts and animated counters from structured data \u2014 deterministic, no AI model needed.",
    "status": "real"
  },
  {
    "kind": "headline_card",
    "name": "Headline / News Card Engine",
    "shelf": "graphics",
    "description": "Renders stylized BREAKING / REPORT / STUDY / COURT RULING cards.",
    "status": "real"
  },
  {
    "kind": "debate_graphics",
    "name": "Debate Graphics Engine",
    "shelf": "graphics",
    "description": "Renders franchise labels: CLAIM, COUNTER, EVIDENCE, REBUTTAL, TRAP, CONCESSION, PERSPECTIVE FLIP, FINAL QUESTION.",
    "status": "real"
  },
  {
    "kind": "caption_engine",
    "name": "Caption Engine",
    "shelf": "graphics",
    "description": "Generates timed captions/subtitles (SRT + styling data) from alignment output, with word-level emphasis support.",
    "status": "real"
  },
  {
    "kind": "typography_engine",
    "name": "Typography Engine",
    "shelf": "graphics",
    "description": "Renders large on-screen text elements (titles, big stat callouts) with font hierarchy, spacing, and positioning.",
    "status": "real"
  },
  {
    "kind": "timeline_engine",
    "name": "Timeline Engine",
    "shelf": "timeline",
    "description": "Core multi-track timeline (video/character/audio/caption/graphics/camera/effects) with add/move/trim/split operations.",
    "status": "real"
  },
  {
    "kind": "transition_engine",
    "name": "Transition Engine",
    "shelf": "timeline",
    "description": "Defines transitions between shots: hard cut (default), zoom, slide, graphic wipe, match transition.",
    "status": "real"
  },
  {
    "kind": "composition_engine",
    "name": "Composition Engine",
    "shelf": "composition",
    "description": "Layers background, characters, lighting, graphics, captions, and effects into a single frame composition spec.",
    "status": "real"
  },
  {
    "kind": "effects_engine",
    "name": "Effects Engine",
    "shelf": "composition",
    "description": "Applies lightweight parameterized effects: blur, glow, shake, vignette, motion blur, screen flash.",
    "status": "real"
  },
  {
    "kind": "preview_renderer",
    "name": "Preview Renderer",
    "shelf": "rendering",
    "description": "Fast, low-resolution render (360p) for checking timing, captions, camera, and lip-sync before a full render.",
    "status": "real"
  },
  {
    "kind": "final_renderer",
    "name": "Final Renderer",
    "shelf": "rendering",
    "description": "Produces the final deliverable: 1080x1920, 30fps, H.264/AAC.",
    "status": "real"
  },
  {
    "kind": "render_queue",
    "name": "Render Queue",
    "shelf": "rendering",
    "description": "Queues multiple episodes for rendering, tracks job status.",
    "status": "real"
  },
  {
    "kind": "render_worker",
    "name": "Render Worker",
    "shelf": "rendering",
    "description": "Executes a single queued render job end to end.",
    "status": "real"
  },
  {
    "kind": "cache_engine",
    "name": "Cache Engine",
    "shelf": "asset_cache",
    "description": "Hashes tool inputs and skips regeneration when nothing changed \u2014 audio, lip-sync, graphics, rendered scenes.",
    "status": "real"
  },
  {
    "kind": "dependency_engine",
    "name": "Dependency Engine",
    "shelf": "asset_cache",
    "description": "Tracks what needs regeneration when an upstream input changes (dialogue edit -> voice -> lip-sync -> captions).",
    "status": "real"
  },
  {
    "kind": "project_manager",
    "name": "Project Manager",
    "shelf": "asset_cache",
    "description": "Scaffolds and manages a self-contained episode project folder (audio/animation/graphics/assets/previews/renders).",
    "status": "real"
  },
  {
    "kind": "asset_cache_store",
    "name": "Asset Cache",
    "shelf": "asset_cache",
    "description": "Stores and looks up reusable franchise-wide assets (rigs, fonts, music, SFX) so episodes don't duplicate them.",
    "status": "real"
  },
  {
    "kind": "production_config",
    "name": "Production Configuration",
    "shelf": "asset_cache",
    "description": "Centralizes render/audio/caption/character default settings in one validated config, instead of hardcoded values.",
    "status": "real"
  },
  {
    "kind": "audio_qc",
    "name": "Audio QC",
    "shelf": "qc",
    "description": "Checks generated audio for clipping, excessive silence, abnormal volume, or corruption.",
    "status": "real"
  },
  {
    "kind": "video_qc",
    "name": "Video QC",
    "shelf": "qc",
    "description": "Checks final video for resolution, frame rate, black frames, missing frames, and audio/video duration mismatch.",
    "status": "real"
  },
  {
    "kind": "lip_sync_qc",
    "name": "Lip-Sync QC",
    "shelf": "qc",
    "description": "Measures audio timing against mouth-shape timing and flags sections with suspicious drift.",
    "status": "real"
  },
  {
    "kind": "scene_qc",
    "name": "Scene QC",
    "shelf": "qc",
    "description": "Checks a scene spec for off-screen characters, caption/graphic collisions, and missing assets.",
    "status": "real"
  },
  {
    "kind": "script_to_video_qc",
    "name": "Script-to-Video QC",
    "shelf": "qc",
    "description": "Compares script, generated voice, and final video to catch accidentally omitted lines.",
    "status": "real"
  },
  {
    "kind": "automated_preview_qc",
    "name": "Automated Preview/QC",
    "shelf": "qc",
    "description": "Runs a checklist against a preview render before committing to an expensive final render.",
    "status": "real"
  },
  {
    "kind": "video_source",
    "name": "Video Source",
    "shelf": "video",
    "description": "Searches yt-dlp-supported video hosts and returns source metadata for clip selection.",
    "status": "real"
  },
  {
    "kind": "pipeline_orchestrator",
    "name": "Pipeline Orchestrator",
    "shelf": "orchestration",
    "description": "Coordinates the full script-to-mp4 pipeline stage by stage: voice -> alignment -> lip-sync -> performance -> graphics -> camera -> timeline -> compositor -> render -> QC.",
    "status": "real"
  }
];

export function getCatalogByShelf() {
  const grouped: Record<string, typeof CATALOG> = {};
  for (const shelfId of Object.keys(SHELVES)) {
    grouped[shelfId] = [];
  }
  for (const entry of CATALOG) {
    if (!grouped[entry.shelf]) grouped[entry.shelf] = [];
    grouped[entry.shelf].push(entry);
  }
  return Object.entries(SHELVES).map(([shelfId, label]) => ({
    shelf: shelfId,
    label,
    tools: grouped[shelfId] || [],
  }));
}
