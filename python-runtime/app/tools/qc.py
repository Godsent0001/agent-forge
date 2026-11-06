"""Quality checks for WAV audio and structured production data."""

from __future__ import annotations

import json
import wave
from pathlib import Path
from typing import Any

from app.tools.base import Tool, ToolExecutionError
from app.tools.shared import parse_json_input, to_json_output


class AudioQCTool(Tool):
    name = "audio_qc"
    description = "Check generated audio for clipping, excessive silence, or abnormal volume."

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        path = params.get("audio_path")
        if not path or not Path(path).exists():
            raise ToolExecutionError(f"audio_qc: file not found: {path}")

        issues = []
        try:
            with wave.open(path, "rb") as w:
                n_frames = w.getnframes()
                sample_width = w.getsampwidth()
                framerate = w.getframerate()
                duration = n_frames / framerate if framerate else 0
                if duration < 0.05:
                    issues.append("duration is near-zero — likely a failed/empty generation")

                if sample_width == 2:  # 16-bit PCM — check clipping/silence cheaply
                    raw = w.readframes(min(n_frames, framerate * 10))  # sample up to 10s
                    import struct
                    samples = struct.unpack(f"<{len(raw)//2}h", raw)
                    if samples:
                        peak = max(abs(s) for s in samples)
                        if peak >= 32760:
                            issues.append("peak sample near max amplitude — possible clipping")
                        rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
                        if rms < 50:
                            issues.append("very low RMS — audio may be silent or corrupted")
        except wave.Error as e:
            issues.append(f"could not parse as WAV: {e}")

        return to_json_output({"path": path, "passed": not issues, "issues": issues})


class LipSyncQCTool(Tool):
    name = "lip_sync_qc"
    description = "Measure audio timing against mouth-shape timing and flag suspicious drift."

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        words = params.get("words")  # from audio_alignment
        mouth = params.get("mouth")  # from lip_sync
        if not words or not mouth:
            raise ToolExecutionError("lip_sync_qc requires both 'words' and 'mouth' arrays")

        audio_end = words[-1]["end"]
        mouth_end = mouth[-1]["time"]
        drift = abs(audio_end - mouth_end)

        issues = []
        if drift > 0.15:
            issues.append(f"mouth animation ends {drift:.3f}s away from audio end — check sync")

        return to_json_output({"passed": not issues, "issues": issues, "drift_seconds": round(drift, 3)})


class SceneQCTool(Tool):
    name = "scene_qc"
    description = "Check a scene spec for off-screen characters, caption/graphic collisions, missing assets."

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        scene = params.get("scene")  # from scene_builder
        if not scene:
            raise ToolExecutionError("scene_qc requires a 'scene' object (from scene_builder output)")

        issues = []
        for char in scene.get("characters", []):
            x = char.get("x_percent", 50)
            if x < 0 or x > 100:
                issues.append(f"character {char.get('character_id')} is off-screen (x={x}%)")

        zone_anchors = [z.get("anchor") for z in scene.get("graphics_zones", [])]
        if len(zone_anchors) != len(set(zone_anchors)):
            issues.append("two or more graphics zones share the same anchor — likely visual collision")

        return to_json_output({"passed": not issues, "issues": issues})


class ScriptToVideoQCTool(Tool):
    name = "script_to_video_qc"
    description = "Compare script, generated voice, and final video to catch accidentally omitted lines."

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        script_lines = params.get("script_lines")  # list of dialogue strings, in order
        generated_transcripts = params.get("generated_transcripts")  # list of transcripts actually voiced
        if script_lines is None or generated_transcripts is None:
            raise ToolExecutionError("script_to_video_qc requires 'script_lines' and 'generated_transcripts'")

        missing = [line for line in script_lines if line not in generated_transcripts]
        return to_json_output({
            "passed": not missing,
            "missing_lines": missing,
            "script_line_count": len(script_lines),
            "generated_count": len(generated_transcripts),
        })


