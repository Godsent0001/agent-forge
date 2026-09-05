"""
Character shelf. Everything except the rig renderer is pure parameter/
timing logic — no rendering happens here, only animation *instructions*,
per the spec's explicit separation ("output what the character does, not
render the character").
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from app.tools.base import Tool, ToolExecutionError
from app.tools.shared import approximate_visemes_for_word, parse_json_input, to_json_output


class LipSyncTool(Tool):
    name = "lip_sync"
    description = "Convert word timing into mouth-shape (viseme) animation data."

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        words = params.get("words")  # from audio_alignment output
        if not words:
            raise ToolExecutionError("lip_sync requires a 'words' array (from audio_alignment output)")

        mouth_frames = []
        for w in words:
            text, start, end = w["text"], w["start"], w["end"]
            visemes = approximate_visemes_for_word(text)
            span = (end - start) / len(visemes)
            for i, viseme in enumerate(visemes):
                mouth_frames.append({"time": round(start + i * span, 3), "shape": viseme})
        mouth_frames.append({"time": words[-1]["end"], "shape": "REST"})

        return to_json_output({"mouth": mouth_frames})


class EyeEngineTool(Tool):
    name = "eye_engine"
    description = "Control gaze direction, blinking, and focus targets."

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        target = params.get("target", "camera")
        duration = params.get("duration", 3.0)
        auto_blink = params.get("auto_blink", True)

        events = [{"type": "gaze", "target": target, "start": 0.0, "duration": duration}]
        if auto_blink:
            t = 0.0
            while t < duration:
                t += random.uniform(2.0, 4.5)  # natural blink interval
                if t < duration:
                    events.append({"type": "blink", "start": round(t, 2), "duration": 0.12})
        return to_json_output({"eye_events": events})


class FacialExpressionTool(Tool):
    name = "facial_expression"
    description = "Produce continuous facial expression parameters from a named state."

    # Named states map to continuous parameter presets, per the spec's
    # explicit instruction not to use simple discrete switches.
    PRESETS = {
        "neutral":    {"confidence": 0.5, "anger": 0.0, "skepticism": 0.0, "smile": 0.1},
        "confident":  {"confidence": 0.85, "anger": 0.05, "skepticism": 0.1, "smile": 0.2},
        "skeptical":  {"confidence": 0.4, "anger": 0.1, "skepticism": 0.75, "smile": 0.0},
        "angry":      {"confidence": 0.6, "anger": 0.8, "skepticism": 0.2, "smile": 0.0},
        "concerned":  {"confidence": 0.3, "anger": 0.1, "skepticism": 0.3, "smile": 0.0},
        "amused":     {"confidence": 0.6, "anger": 0.0, "skepticism": 0.1, "smile": 0.7},
        "surprised":  {"confidence": 0.3, "anger": 0.0, "skepticism": 0.2, "smile": 0.15},
        "thinking":   {"confidence": 0.4, "anger": 0.0, "skepticism": 0.4, "smile": 0.05},
        "dismissive": {"confidence": 0.7, "anger": 0.3, "skepticism": 0.6, "smile": 0.1},
        "serious":    {"confidence": 0.65, "anger": 0.2, "skepticism": 0.3, "smile": 0.0},
    }

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        state = params.get("state", "neutral")
        intensity = params.get("intensity", 1.0)
        preset = self.PRESETS.get(state)
        if preset is None:
            raise ToolExecutionError(
                f"Unknown expression state '{state}'. Known: {', '.join(self.PRESETS)}"
            )
        scaled = {k: round(v * intensity, 3) for k, v in preset.items()}
        return to_json_output({"expression": scaled, "state": state})


class FacialPerformanceTool(Tool):
    name = "facial_performance"
    description = "Combine dialogue, emotion, and context into facial behavior instructions."

    # Very small heuristic set of dialogue -> facial-beat triggers.
    TRIGGERS = [
        (("exactly", "precisely"), ["eyebrow_raise", "eye_contact"]),
        (("assum", "claim"), ["eyebrow_raise", "slight_head_tilt"]),
        (("?",), ["eyebrow_raise", "head_tilt"]),
        (("ridiculous", "wrong", "false"), ["head_shake", "eyebrow_raise"]),
    ]

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        text = params.get("dialogue", "").lower()
        emotion = params.get("emotion", "neutral")

        beats: list[str] = []
        for keywords, actions in self.TRIGGERS:
            if any(k in text for k in keywords):
                beats.extend(actions)
        if not beats:
            beats = ["eye_contact"]

        return to_json_output({
            "facial_behavior": list(dict.fromkeys(beats)),  # de-dupe, preserve order
            "base_expression": emotion,
        })


class GestureEngineTool(Tool):
    name = "gesture_engine"
    description = "Produce hand/arm gesture animation instructions from a reusable library."

    LIBRARY = [
        "open_hand", "point", "count", "emphasize", "dismiss",
        "raise_hand", "shrug", "fold_arms", "present", "question",
    ]

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        gesture = params.get("gesture")
        duration = params.get("duration", 1.2)
        if gesture not in self.LIBRARY:
            raise ToolExecutionError(f"Unknown gesture '{gesture}'. Library: {', '.join(self.LIBRARY)}")

        # Every gesture is broken into named phases so motion doesn't look
        # robotic (start/anticipation/main/hold/recovery), per the spec.
        phase_weights = {"start": 0.1, "anticipation": 0.15, "main": 0.35, "hold": 0.25, "recovery": 0.15}
        t = 0.0
        phases = []
        for phase, weight in phase_weights.items():
            span = duration * weight
            phases.append({"phase": phase, "start": round(t, 3), "duration": round(span, 3)})
            t += span

        return to_json_output({"gesture": gesture, "phases": phases, "total_duration": duration})


class BodyPoseTool(Tool):
    name = "body_pose"
    description = "Control a character's overall body stance and pose transitions."

    POSES = [
        "neutral", "confident", "relaxed", "lean_forward", "lean_back",
        "cross_arms", "thinking", "aggressive", "defensive",
    ]

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        target_pose = params.get("pose")
        transition_duration = params.get("transition_duration", 0.6)
        if target_pose not in self.POSES:
            raise ToolExecutionError(f"Unknown pose '{target_pose}'. Known: {', '.join(self.POSES)}")

        return to_json_output({
            "pose": target_pose,
            "transition": {"type": "ease_in_out", "duration": transition_duration},
        })


class CharacterPerformanceTool(Tool):
    name = "character_performance"
    description = "Combine lip-sync, face, eyes, gesture, and body into one performance timeline."

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        required = ["emotion", "intent", "gaze"]
        missing = [k for k in required if k not in params]
        if missing:
            raise ToolExecutionError(f"character_performance missing fields: {missing}")

        # This composes the *instructions* the other character tools would
        # be called with — the actual sub-timelines come from calling
        # lip_sync / eye_engine / gesture_engine / body_pose / facial_*
        # separately and merging their outputs; this tool defines the plan.
        plan = {
            "facial_expression": {"state": params["emotion"], "intensity": params.get("intensity", 0.75)},
            "eye_engine": {"target": params["gaze"], "duration": params.get("duration", 3.0)},
            "gesture_engine": {"gesture": params.get("gesture"), "duration": params.get("gesture_duration", 1.2)}
                              if params.get("gesture") else None,
            "body_pose": {"pose": params.get("pose", "neutral")},
        }
        return to_json_output({"performance_plan": {k: v for k, v in plan.items() if v is not None}})


class CharacterAssetManagerTool(Tool):
    name = "character_asset_manager"
    description = "Look up and validate a character's reusable rig/voice/texture assets."

    EXPECTED_SUBDIRS = ["model", "rig", "expressions", "gestures", "textures", "voices"]

    def __init__(self, characters_dir: str = "./assets/characters"):
        self._root = Path(characters_dir)

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        character_id = params.get("character_id")
        if not character_id:
            raise ToolExecutionError("character_asset_manager requires 'character_id'")

        char_dir = self._root / character_id
        report = {sub: (char_dir / sub).exists() for sub in self.EXPECTED_SUBDIRS}
        missing = [k for k, present in report.items() if not present]

        return to_json_output({
            "character_id": character_id,
            "path": str(char_dir),
            "assets_present": report,
            "valid": not missing,
            "missing": missing,
        })


class CharacterRigTool(Tool):
    name = "character_rig"
    description = "Render a character performance timeline into animated frames via Rive."

    async def execute(self, input: str, *, context: Any) -> str:
        raise ToolExecutionError(
            "character_rig is a stub: rendering a performance timeline into actual "
            "pixels needs a Rive (.riv) rig asset + the Rive runtime (rive-python "
            "or driving Rive's C++ runtime headlessly). Every upstream input this "
            "tool would consume — lip-sync visemes, facial/eye/gesture/body "
            "parameters — is already produced by the other Character-shelf tools "
            "in real, working form; only this final render-to-pixels step is "
            "unimplemented. Wire a .riv state machine whose inputs match this "
            "tool's expected parameters (viseme, confidence, anger, gaze_x/y, "
            "gesture, pose) and swap this stub for a real Rive call."
        )
