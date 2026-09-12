"""Scene shelf. All pure data/JSON logic — no rendering."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.tools.base import Tool, ToolExecutionError
from app.tools.shared import parse_json_input, to_json_output


class SceneTemplateManagerTool(Tool):
    name = "scene_template_manager"
    description = "Manage reusable environment templates (background, lighting, camera, prop zones)."

    def __init__(self, templates_dir: str = "./assets/scene_templates"):
        self._root = Path(templates_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        action = params.get("action", "get")  # get | save | list
        template_id = params.get("template_id")

        if action == "list":
            return to_json_output({"templates": [p.stem for p in self._root.glob("*.json")]})

        if action == "save":
            if not template_id or "template" not in params:
                raise ToolExecutionError("save requires 'template_id' and 'template'")
            (self._root / f"{template_id}.json").write_text(json.dumps(params["template"], indent=2))
            return to_json_output({"saved": template_id})

        if action == "get":
            if not template_id:
                raise ToolExecutionError("get requires 'template_id'")
            path = self._root / f"{template_id}.json"
            if not path.exists():
                raise ToolExecutionError(f"No such template: {template_id}")
            return path.read_text()

        raise ToolExecutionError(f"Unknown action '{action}'. Use get, save, or list.")


class SceneBuilderTool(Tool):
    name = "scene_builder"
    description = "Assemble a scene from a production spec: character placement, camera, graphics zones."

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        characters = params.get("characters", [])
        if not characters:
            raise ToolExecutionError("scene_builder requires a non-empty 'characters' array")

        # Default two-character debate framing: A at 30%, B at 70%, per spec's example.
        n = len(characters)
        positions = []
        for i, char in enumerate(characters):
            x_pct = round((i + 1) / (n + 1) * 100, 1)
            positions.append({"character_id": char.get("id", f"char_{i}"), "x_percent": x_pct})

        scene = {
            "characters": positions,
            "camera": params.get("camera", {"shot": "two_shot"}),
            "graphics_zones": params.get("graphics_zones", [
                {"name": "evidence_card", "anchor": "center"},
                {"name": "caption", "anchor": "bottom"},
            ]),
        }
        return to_json_output(scene)


class LightingEngineTool(Tool):
    name = "lighting_engine"
    description = "Select a lighting mood preset based on the moment in the script."

    # Maps semantic script moments -> lighting presets, per spec examples.
    PRESETS = {
        "normal": {"contrast": 1.0, "warmth": 0.5, "key_intensity": 1.0},
        "dramatic": {"contrast": 1.35, "warmth": 0.4, "key_intensity": 1.15},
        "evidence": {"contrast": 1.1, "warmth": 0.55, "key_intensity": 1.05},
        "tension": {"contrast": 1.25, "warmth": 0.3, "key_intensity": 1.1},
        "final": {"contrast": 1.2, "warmth": 0.45, "key_intensity": 1.1},
    }
    MOMENT_TO_PRESET = {
        "trap": "dramatic", "attack": "dramatic",
        "concession": "normal",
        "evidence": "evidence",
        "final_dilemma": "final", "final": "final",
    }

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        preset_name = params.get("preset")
        moment = params.get("moment")

        if not preset_name and moment:
            preset_name = self.MOMENT_TO_PRESET.get(moment, "normal")
        preset_name = preset_name or "normal"

        preset = self.PRESETS.get(preset_name)
        if preset is None:
            raise ToolExecutionError(f"Unknown lighting preset '{preset_name}'. Known: {', '.join(self.PRESETS)}")

        return to_json_output({"preset": preset_name, "lighting": preset})


import re
from PIL import Image, ImageDraw, ImageFont


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[-\s]+", "_", text)


class EnvironmentDesignerTool(Tool):
    name = "environment_designer"
    description = "Create reusable visual environment assets (debate hall, presidential stage, TV studio, courtroom, etc.)."

    def __init__(self, environments_dir: str = "./assets/environments"):
        self._root = Path(environments_dir)

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        name = params.get("name") or "Debate Stage"
        env_id = params.get("environment_id") or params.get("id") or _slugify(name)
        env_type = params.get("type") or params.get("preset") or "debate_hall"
        desc = params.get("description", "")
        lighting_preset = params.get("lighting_preset", "dramatic")

        env_dir = self._root / env_id
        env_dir.mkdir(parents=True, exist_ok=True)

        metadata = {
            "environment_id": env_id,
            "name": name,
            "type": env_type,
            "description": desc,
            "lighting_preset": lighting_preset,
            "visual_style": params.get("visual_style", "2D vector/cartoon"),
        }

        meta_path = env_dir / "metadata.json"
        meta_path.write_text(json.dumps(metadata, indent=2))

        asset_path = str(env_dir / "asset.png")
        w, h = 1920, 1080
        img = Image.new("RGB", (w, h), color=(15, 23, 42))
        draw = ImageDraw.Draw(img)

        # Environment backdrop graphics based on type
        if env_type in ["presidential_stage", "debate_hall"]:
            # Dark background with spotlight beams & podium silhouettes
            draw.rectangle([0, 0, w, h], fill=(15, 23, 42))
            draw.polygon([(0, 0), (w // 3, h), (0, h)], fill=(30, 58, 138))
            draw.polygon([(w, 0), (2 * w // 3, h), (w, h)], fill=(30, 58, 138))
            draw.rectangle([100, h - 250, w - 100, h - 50], fill=(30, 41, 59), outline=(99, 102, 241), width=4)
        elif env_type == "tv_studio":
            draw.rectangle([0, 0, w, h], fill=(24, 24, 27))
            draw.rectangle([200, 150, w - 200, h - 300], fill=(39, 39, 42), outline=(168, 85, 247), width=6)
            draw.text((w // 2, 250), "STUDIO BROADCAST", fill=(168, 85, 247), anchor="ms")
        elif env_type == "courtroom":
            draw.rectangle([0, 0, w, h], fill=(69, 26, 3))
            draw.rectangle([100, h - 350, w - 100, h - 50], fill=(120, 53, 15), outline=(217, 119, 6), width=6)
        else:
            # Generic stage / hall
            draw.rectangle([0, 0, w, h], fill=(30, 41, 59))
            draw.rectangle([50, 50, w - 50, h - 50], outline=(148, 163, 184), width=4)

        # Title overlay
        try:
            font_title = ImageFont.truetype("DejaVuSans-Bold.ttf", 48)
            font_sub = ImageFont.truetype("DejaVuSans.ttf", 28)
        except OSError:
            font_title = font_sub = ImageFont.load_default()

        draw.text((w // 2, h // 2 - 20), name.upper(), fill=(255, 255, 255), font=font_title, anchor="ms")
        draw.text((w // 2, h // 2 + 40), f"Environment Type: {env_type} | Lighting: {lighting_preset}", fill=(203, 213, 225), font=font_sub, anchor="ms")

        img.save(asset_path)

        return to_json_output({
            "environment_id": env_id,
            "name": name,
            "type": env_type,
            "metadata_path": str(meta_path),
            "asset_path": asset_path,
            "status": "created",
        })
