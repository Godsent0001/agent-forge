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
