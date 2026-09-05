"""
Pipeline Orchestrator. Per the spec: "it shouldn't contain the actual
implementation of each operation" — it just tracks pipeline stage order
and, given which stages have already produced output, answers "what
needs to happen next?"

As a Tool, it doesn't call the other tools itself (that's the AI agent's
job when this is attached to an agent as one of its tools — the agent
reasons about which stage to run and calls that stage's tool directly,
using this orchestrator to check sequencing/completeness). This keeps
the orchestrator a pure sequencing helper, not a hidden second execution
engine competing with the one in app/runtime/engine.py.
"""

from __future__ import annotations

from typing import Any

from app.tools.base import Tool, ToolExecutionError
from app.tools.shared import parse_json_input, to_json_output

STAGES = [
    "voice_generator", "audio_processing", "audio_alignment",
    "lip_sync", "character_performance",
    "scene_builder", "camera_director",
    "evidence_graphics", "caption_engine",
    "timeline_engine", "composition_engine",
    "preview_renderer", "automated_preview_qc",
    "final_renderer", "video_qc",
]


class PipelineOrchestratorTool(Tool):
    name = "pipeline_orchestrator"
    description = "Coordinate the full script-to-mp4 pipeline stage by stage."

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        completed = set(params.get("completed_stages", []))

        unknown = completed - set(STAGES)
        if unknown:
            raise ToolExecutionError(f"Unknown stage(s) in completed_stages: {sorted(unknown)}")

        remaining = [s for s in STAGES if s not in completed]
        next_stage = remaining[0] if remaining else None

        return to_json_output({
            "next_stage": next_stage,
            "remaining_stages": remaining,
            "completed_stages": sorted(completed),
            "progress": f"{len(completed)}/{len(STAGES)}",
            "done": next_stage is None,
        })
