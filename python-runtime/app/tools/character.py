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

from PIL import Image, ImageDraw, ImageFont
from app.tools.base import Tool, ToolExecutionError
from app.tools.rendering import _run_ffmpeg_from_image_and_audio
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
            span = (end - start) / max(len(visemes), 1)
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
            "facial_behavior": list(dict.fromkeys(beats)),
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

        plan = {
            "facial_expression": {"state": params["emotion"], "intensity": params.get("intensity", 0.75)},
            "eye_engine": {"target": params["gaze"], "duration": params.get("duration", 3.0)},
            "gesture_engine": {"gesture": params.get("gesture"), "duration": params.get("gesture_duration", 1.2)}
                              if params.get("gesture") else None,
            "body_pose": {"pose": params.get("pose", "neutral")},
        }
        return to_json_output({"performance_plan": {k: v for k, v in plan.items() if v is not None}})


import json
import re

EXPECTED_CHARACTER_SUBDIRS = ["model", "rig", "expressions", "gestures", "textures", "voices"]


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[-\s]+", "_", text)


def _get_skin_color(skin_tone: str) -> tuple[int, int, int]:
    tone = (skin_tone or "").lower()
    if any(k in tone for k in ["dark", "nigerian", "black", "deep"]):
        return (112, 72, 45)
    if any(k in tone for k in ["fair", "light", "pale", "white"]):
        return (245, 215, 190)
    if any(k in tone for k in ["tan", "olive", "medium", "brown"]):
        return (195, 140, 95)
    return (180, 130, 90)


def _get_clothing_color(clothing: str) -> tuple[int, int, int]:
    cl = (clothing or "").lower()
    if "navy" in cl or "blue" in cl:
        return (30, 58, 138)
    if "red" in cl or "maroon" in cl:
        return (153, 27, 27)
    if "green" in cl:
        return (20, 83, 45)
    if "black" in cl or "dark" in cl:
        return (30, 41, 59)
    if "grey" in cl or "gray" in cl:
        return (71, 85, 105)
    return (51, 65, 85)


def _render_character_asset(
    profile: dict[str, Any],
    expression: str = "neutral",
    pose: str = "standing",
    gesture: str | None = None,
    width: int = 720,
    height: int = 1280,
    output_path: str = "./output/character_asset.png",
) -> str:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    name = profile.get("name") or profile.get("character_id") or "Character"
    skin_tone = profile.get("skin_tone", "medium")
    hair_desc = str(profile.get("hair", "")).lower()
    clothing_desc = str(profile.get("clothing", "")).lower()
    distinctive = [str(f).lower() for f in profile.get("distinctive_features", [])]
    accessories = [str(a).lower() for a in profile.get("accessories", [])]

    is_bald = "bald" in hair_desc
    has_beard = any("beard" in f or "beard" in hair_desc for f in distinctive + accessories)
    has_glasses = any("glasses" in f or "glasses" in hair_desc for f in distinctive + accessories)

    skin_rgb = _get_skin_color(skin_tone)
    suit_rgb = _get_clothing_color(clothing_desc)

    img = Image.new("RGB", (width, height), color=(245, 247, 250))
    draw = ImageDraw.Draw(img)

    # Frame card
    draw.rectangle([20, 20, width - 20, height - 20], outline=(203, 213, 225), width=4)
    draw.rectangle([40, 40, width - 40, height - 40], fill=(255, 255, 255), outline=(226, 232, 240), width=2)

    center_x = width // 2
    head_y = height // 3

    # Torso / Outfit
    draw.polygon([
        (center_x - 160, head_y + 180),
        (center_x + 160, head_y + 180),
        (center_x + 210, height - 180),
        (center_x - 210, height - 180),
    ], fill=suit_rgb)

    # Collar / Shirt
    draw.polygon([
        (center_x - 40, head_y + 180),
        (center_x + 40, head_y + 180),
        (center_x, head_y + 260),
    ], fill=(255, 255, 255))

    # Neck
    draw.rectangle([center_x - 45, head_y + 110, center_x + 45, head_y + 185], fill=skin_rgb)

    # Head
    draw.ellipse([center_x - 110, head_y - 120, center_x + 110, head_y + 120], fill=skin_rgb)

    # Hair (if not bald)
    if not is_bald:
        draw.chord([center_x - 115, head_y - 130, center_x + 115, head_y - 20], start=180, end=360, fill=(30, 27, 24))

    # Beard
    if has_beard:
        draw.chord([center_x - 100, head_y - 20, center_x + 100, head_y + 120], start=0, end=180, fill=(30, 27, 24))

    # Eyes & Eyebrows
    eye_y = head_y - 15
    brow_y = eye_y - 25

    if expression == "skeptical":
        draw.line([center_x - 65, brow_y - 10, center_x - 20, brow_y - 5], fill=(30, 27, 24), width=5)
        draw.line([center_x + 20, brow_y - 20, center_x + 65, brow_y - 30], fill=(30, 27, 24), width=5)
    elif expression in ["angry", "serious"]:
        draw.line([center_x - 65, brow_y - 20, center_x - 20, brow_y - 5], fill=(30, 27, 24), width=5)
        draw.line([center_x + 20, brow_y - 5, center_x + 65, brow_y - 20], fill=(30, 27, 24), width=5)
    else:
        draw.line([center_x - 65, brow_y - 10, center_x - 20, brow_y - 10], fill=(30, 27, 24), width=5)
        draw.line([center_x + 20, brow_y - 10, center_x + 65, brow_y - 10], fill=(30, 27, 24), width=5)

    draw.ellipse([center_x - 55, eye_y - 12, center_x - 25, eye_y + 12], fill=(255, 255, 255))
    draw.ellipse([center_x + 25, eye_y - 12, center_x + 55, eye_y + 12], fill=(255, 255, 255))
    draw.ellipse([center_x - 45, eye_y - 8, center_x - 35, eye_y + 8], fill=(30, 41, 59))
    draw.ellipse([center_x + 35, eye_y - 8, center_x + 45, eye_y + 8], fill=(30, 41, 59))

    # Glasses
    if has_glasses:
        draw.rectangle([center_x - 65, eye_y - 18, center_x - 15, eye_y + 18], outline=(15, 23, 42), width=4)
        draw.rectangle([center_x + 15, eye_y - 18, center_x + 65, eye_y + 18], outline=(15, 23, 42), width=4)
        draw.line([center_x - 15, eye_y, center_x + 15, eye_y], fill=(15, 23, 42), width=4)

    # Nose
    draw.line([center_x, head_y + 5, center_x - 8, head_y + 30, center_x + 8, head_y + 30], fill=(140, 90, 60), width=3)

    # Mouth
    mouth_y = head_y + 55
    if expression in ["amused", "confident", "happy"]:
        draw.arc([center_x - 35, mouth_y - 15, center_x + 35, mouth_y + 20], start=0, end=180, fill=(185, 28, 28), width=5)
    elif expression in ["angry", "concerned", "skeptical"]:
        draw.line([center_x - 30, mouth_y + 10, center_x + 30, mouth_y - 5], fill=(185, 28, 28), width=5)
    else:
        draw.line([center_x - 30, mouth_y, center_x + 30, mouth_y], fill=(185, 28, 28), width=5)

    # Labels
    try:
        font_title = ImageFont.truetype("DejaVuSans-Bold.ttf", 36)
        font_sub = ImageFont.truetype("DejaVuSans.ttf", 24)
    except OSError:
        font_title = font_sub = ImageFont.load_default()

    draw.text((center_x, height - 130), name, fill=(15, 23, 42), font=font_title, anchor="ms")
    details_str = f"Expression: {expression.capitalize()} | Pose: {pose}"
    if gesture:
        details_str += f" | Gesture: {gesture}"
    draw.text((center_x, height - 85), details_str, fill=(71, 85, 105), font=font_sub, anchor="ms")
    draw.text((center_x, height - 50), f"ID: {profile.get('character_id', 'unknown')}", fill=(148, 163, 184), font=font_sub, anchor="ms")

    img.save(output_path)
    return output_path


class CharacterDesignerTool(Tool):
    name = "character_designer"
    description = "Create a unique character from detailed attributes, generating reusable character files and visual assets."

    def __init__(self, characters_dir: str = "./assets/characters"):
        self._root = Path(characters_dir)

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        name = params.get("name") or "Character"
        character_id = params.get("character_id") or _slugify(name)

        char_dir = self._root / character_id
        char_dir.mkdir(parents=True, exist_ok=True)
        for sub in EXPECTED_CHARACTER_SUBDIRS:
            (char_dir / sub).mkdir(parents=True, exist_ok=True)

        distinctive = params.get("distinctive_features") or []
        if isinstance(distinctive, str):
            distinctive = [distinctive]

        accessories = params.get("accessories") or []
        if isinstance(accessories, str):
            accessories = [accessories]

        profile = {
            "character_id": character_id,
            "name": name,
            "description": params.get("description", ""),
            "gender": params.get("gender", "unspecified"),
            "age": params.get("age", "adult"),
            "height": params.get("height", "average"),
            "body_build": params.get("body_build", "average"),
            "skin_tone": params.get("skin_tone", "medium"),
            "face_shape": params.get("face_shape", "oval"),
            "hair": params.get("hair", "short brown"),
            "eyes": params.get("eyes", "brown"),
            "eyebrows": params.get("eyebrows", "default"),
            "nose": params.get("nose", "default"),
            "mouth": params.get("mouth", "default"),
            "ears": params.get("ears", "default"),
            "clothing": params.get("clothing", "casual suit"),
            "shoes": params.get("shoes", "shoes"),
            "accessories": accessories,
            "distinctive_features": distinctive,
            "visual_style": params.get("visual_style", "2D vector/cartoon"),
        }

        profile_path = char_dir / "profile.json"
        profile_path.write_text(json.dumps(profile, indent=2))

        asset_path = str(char_dir / "asset.png")
        preview_path = str(char_dir / "preview.png")
        _render_character_asset(profile, expression="neutral", pose="standing", output_path=asset_path)
        _render_character_asset(profile, expression="neutral", pose="standing", output_path=preview_path)

        return to_json_output({
            "character_id": character_id,
            "name": name,
            "profile": profile,
            "profile_path": str(profile_path),
            "asset_path": asset_path,
            "preview_path": preview_path,
            "status": "created",
        })


class CharacterAssetManagerTool(Tool):
    name = "character_asset_manager"
    description = "Save, load, update, list, and delete character assets and metadata by permanent ID."

    def __init__(self, characters_dir: str = "./assets/characters"):
        self._root = Path(characters_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        action = params.get("action", "get")  # get | load | save | create | update | delete | list | validate
        character_id = params.get("character_id")

        if action in ["list", "list_characters"]:
            characters = []
            for p in self._root.iterdir():
                if p.is_dir():
                    profile_file = p / "profile.json"
                    if profile_file.exists():
                        try:
                            characters.append(json.loads(profile_file.read_text()))
                        except Exception:
                            characters.append({"character_id": p.name})
                    else:
                        characters.append({"character_id": p.name})
            return to_json_output({"characters": characters, "count": len(characters)})

        if action in ["get", "load"]:
            if not character_id:
                raise ToolExecutionError("character_asset_manager 'get' requires 'character_id'")
            char_dir = self._root / character_id
            profile_file = char_dir / "profile.json"
            if not char_dir.exists() or not profile_file.exists():
                raise ToolExecutionError(f"Character '{character_id}' not found.")
            profile = json.loads(profile_file.read_text())
            report = {sub: (char_dir / sub).exists() for sub in EXPECTED_CHARACTER_SUBDIRS}
            return to_json_output({
                "character_id": character_id,
                "profile": profile,
                "path": str(char_dir),
                "asset_path": str(char_dir / "asset.png"),
                "preview_path": str(char_dir / "preview.png"),
                "assets_present": report,
            })

        if action in ["save", "create", "update"]:
            if not character_id:
                raise ToolExecutionError("character_asset_manager 'save' requires 'character_id'")
            profile = params.get("profile") or params.get("data")
            if not profile:
                raise ToolExecutionError("character_asset_manager 'save' requires 'profile' or 'data'")
            char_dir = self._root / character_id
            char_dir.mkdir(parents=True, exist_ok=True)
            for sub in EXPECTED_CHARACTER_SUBDIRS:
                (char_dir / sub).mkdir(parents=True, exist_ok=True)
            profile_path = char_dir / "profile.json"
            profile_path.write_text(json.dumps(profile, indent=2))
            return to_json_output({"character_id": character_id, "status": "saved", "path": str(profile_path)})

        if action == "delete":
            if not character_id:
                raise ToolExecutionError("character_asset_manager 'delete' requires 'character_id'")
            char_dir = self._root / character_id
            if char_dir.exists():
                import shutil
                shutil.rmtree(char_dir)
                return to_json_output({"character_id": character_id, "status": "deleted"})
            return to_json_output({"character_id": character_id, "status": "not_found"})

        if action == "validate":
            if not character_id:
                raise ToolExecutionError("character_asset_manager 'validate' requires 'character_id'")
            char_dir = self._root / character_id
            report = {sub: (char_dir / sub).exists() for sub in EXPECTED_CHARACTER_SUBDIRS}
            missing = [k for k, present in report.items() if not present]
            return to_json_output({
                "character_id": character_id,
                "path": str(char_dir),
                "assets_present": report,
                "valid": not missing,
                "missing": missing,
            })

        raise ToolExecutionError(f"Unknown action '{action}' for character_asset_manager")


class CharacterPreviewTool(Tool):
    name = "character_preview"
    description = "Visually inspect a character in different poses and expressions before animation."

    def __init__(self, characters_dir: str = "./assets/characters"):
        self._root = Path(characters_dir)

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        character_id = params.get("character_id") or params.get("character_name")
        if not character_id:
            raise ToolExecutionError("character_preview requires 'character_id'")

        character_id = _slugify(character_id)
        char_dir = self._root / character_id
        profile_file = char_dir / "profile.json"

        if profile_file.exists():
            try:
                profile = json.loads(profile_file.read_text())
            except Exception:
                profile = {"character_id": character_id, "name": character_id}
        else:
            profile = {"character_id": character_id, "name": character_id}

        expression = params.get("expression", "neutral")
        pose = params.get("pose", "standing")
        gesture = params.get("gesture")
        out_path = params.get("output_path") or f"./output/character_preview_{character_id}.png"

        rendered_path = _render_character_asset(
            profile=profile,
            expression=expression,
            pose=pose,
            gesture=gesture,
            output_path=out_path,
        )

        return to_json_output({
            "character_id": character_id,
            "expression": expression,
            "pose": pose,
            "gesture": gesture,
            "image_path": rendered_path,
            "status": "rendered_preview",
        })


class CharacterRigTool(Tool):
    name = "character_rig"
    description = "Turn a character asset into an animated performance frame/video using its stored character profile."

    def __init__(self, characters_dir: str = "./assets/characters"):
        self._root = Path(characters_dir)

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        character_id = params.get("character_id") or params.get("character_name") or "julian"
        slug_id = _slugify(character_id)

        char_dir = self._root / slug_id
        profile_file = char_dir / "profile.json"

        if profile_file.exists():
            try:
                profile = json.loads(profile_file.read_text())
            except Exception:
                profile = {"character_id": slug_id, "name": character_id}
        else:
            profile = {"character_id": slug_id, "name": character_id}

        expression = params.get("expression") or params.get("emotion") or "neutral"
        gesture = params.get("gesture", "default stance")
        pose = params.get("pose", "standing")
        output_image_path = params.get("output_image_path", f"./output/character_rig_{slug_id}.png")
        output_video_path = params.get("output_video_path", f"./output/character_rig_{slug_id}.mp4")
        audio_path = params.get("audio_path")

        _render_character_asset(
            profile=profile,
            expression=expression,
            pose=pose,
            gesture=gesture,
            output_path=output_image_path,
        )

        # Attempt to assemble a preview video if ffmpeg is available
        video_generated = False
        try:
            await _run_ffmpeg_from_image_and_audio(
                image_path=output_image_path,
                audio_path=audio_path,
                out_path=output_video_path,
                width=720,
                height=1280,
                fps=24,
                fallback_duration=3.0,
            )
            video_generated = True
        except Exception:
            video_generated = False

        result = {
            "character_id": slug_id,
            "character_name": profile.get("name", character_id),
            "expression": expression,
            "gesture": gesture,
            "pose": pose,
            "image_path": output_image_path,
            "status": "rendered_character_rig",
        }
        if video_generated:
            result["video_path"] = output_video_path

        return to_json_output(result)
