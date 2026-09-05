"""
Timeline shelf. The Timeline Engine is pure data-structure logic (a list
of clips per track with add/move/trim/split), matching the spec's
"core infrastructure" description — this is what every other engine's
output eventually gets placed onto.
"""

from __future__ import annotations

from typing import Any

from app.tools.base import Tool, ToolExecutionError
from app.tools.shared import parse_json_input, to_json_output

TRACKS = ["VIDEO", "CHARACTER", "AUDIO", "CAPTION", "GRAPHICS", "CAMERA", "EFFECTS"]


class TimelineEngineTool(Tool):
    name = "timeline_engine"
    description = "Core multi-track timeline: add/move/trim/split clips across tracks."

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        op = params.get("op")
        timeline = params.get("timeline", {t: [] for t in TRACKS})

        if op == "add":
            track, clip = params.get("track"), params.get("clip")
            if track not in TRACKS or not clip or "start" not in clip or "duration" not in clip:
                raise ToolExecutionError(
                    f"add requires 'track' in {TRACKS} and a 'clip' with 'start'/'duration'"
                )
            timeline.setdefault(track, []).append(clip)
            timeline[track].sort(key=lambda c: c["start"])

        elif op == "move":
            track, clip_id, new_start = params.get("track"), params.get("clip_id"), params.get("new_start")
            clip = next((c for c in timeline.get(track, []) if c.get("id") == clip_id), None)
            if not clip:
                raise ToolExecutionError(f"No clip '{clip_id}' on track '{track}'")
            clip["start"] = new_start
            timeline[track].sort(key=lambda c: c["start"])

        elif op == "trim":
            track, clip_id, new_duration = params.get("track"), params.get("clip_id"), params.get("new_duration")
            clip = next((c for c in timeline.get(track, []) if c.get("id") == clip_id), None)
            if not clip:
                raise ToolExecutionError(f"No clip '{clip_id}' on track '{track}'")
            clip["duration"] = new_duration

        elif op == "split":
            track, clip_id, split_at = params.get("track"), params.get("clip_id"), params.get("split_at")
            clips = timeline.get(track, [])
            clip = next((c for c in clips if c.get("id") == clip_id), None)
            if not clip:
                raise ToolExecutionError(f"No clip '{clip_id}' on track '{track}'")
            if not (clip["start"] < split_at < clip["start"] + clip["duration"]):
                raise ToolExecutionError("split_at must fall strictly within the clip's span")
            first_duration = split_at - clip["start"]
            second = dict(clip)
            second["id"] = f"{clip_id}_b"
            second["start"] = split_at
            second["duration"] = clip["duration"] - first_duration
            clip["id"] = f"{clip_id}_a"
            clip["duration"] = first_duration
            clips.append(second)
            clips.sort(key=lambda c: c["start"])

        elif op == "remove":
            track, clip_id = params.get("track"), params.get("clip_id")
            timeline[track] = [c for c in timeline.get(track, []) if c.get("id") != clip_id]

        elif op != "get":
            raise ToolExecutionError(f"Unknown op '{op}'. Use add, move, trim, split, remove, or get.")

        total_duration = max(
            (c["start"] + c["duration"] for track in timeline.values() for c in track),
            default=0.0,
        )
        return to_json_output({"timeline": timeline, "total_duration": total_duration})


class TransitionEngineTool(Tool):
    name = "transition_engine"
    description = "Define transitions between shots: hard cut (default), zoom, slide, graphic wipe."

    VALID = {"cut", "zoom", "slide", "graphic_wipe", "match"}

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        transition = params.get("transition", "cut")
        duration = params.get("duration", 0.0 if transition == "cut" else 0.4)

        if transition not in self.VALID:
            raise ToolExecutionError(f"Unknown transition '{transition}'. Known: {', '.join(self.VALID)}")

        return to_json_output({"transition": transition, "duration": duration})
