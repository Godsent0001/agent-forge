"""Camera shelf. Rule-based shot selection + movement instruction generation."""

from __future__ import annotations

from typing import Any

from app.tools.base import Tool, ToolExecutionError
from app.tools.shared import parse_json_input, to_json_output


class CameraDirectorTool(Tool):
    name = "camera_director"
    description = "Automatically select a shot type from the dialogue's semantic beat."

    # Semantic beat -> shot, per spec's explicit examples.
    BEAT_TO_SHOT = {
        "concession": "A_MEDIUM",
        "attack": "A_CLOSE",
        "trap": "A_CLOSE",
        "evidence": "EVIDENCE",
        "final": "TWO_SHOT",
        "neutral": "TWO_SHOT",
        "rebuttal": "B_CLOSE",
    }
    VALID_SHOTS = {"TWO_SHOT", "A_CLOSE", "B_CLOSE", "A_MEDIUM", "B_MEDIUM", "SPLIT_SCREEN", "WIDE", "EVIDENCE", "FINAL"}

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        beat = params.get("beat", "neutral")
        speaker = params.get("speaker")  # "A" | "B" — used to resolve A_CLOSE vs B_CLOSE

        shot = self.BEAT_TO_SHOT.get(beat, "TWO_SHOT")
        if speaker == "B":
            shot = shot.replace("A_", "B_")

        if shot not in self.VALID_SHOTS:
            raise ToolExecutionError(f"Resolved shot '{shot}' is not a recognized shot type")

        return to_json_output({"shot": shot, "beat": beat})


class CameraAnimationTool(Tool):
    name = "camera_animation"
    description = "Produce camera movement instructions: pan, push, pull, tilt, tracking, focus, shake."

    VALID_MOVEMENTS = {"pan", "push_in", "pull_out", "tilt", "track", "focus_pull", "shake", "static"}

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        movement = params.get("movement", "static")
        duration = params.get("duration", 1.2)
        amount = params.get("amount", 0.15)

        if movement not in self.VALID_MOVEMENTS:
            raise ToolExecutionError(f"Unknown movement '{movement}'. Known: {', '.join(self.VALID_MOVEMENTS)}")

        return to_json_output({"movement": movement, "duration": duration, "amount": amount})
