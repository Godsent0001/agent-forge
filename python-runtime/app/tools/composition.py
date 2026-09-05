"""
Composition shelf. Composition Engine does real pixel compositing via PIL
(layering background + character stills/graphics/captions into one
frame) — testable without a video pipeline. Effects Engine produces
ffmpeg filter graphs and can apply them directly to an image or video.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from app.tools.base import Tool, ToolExecutionError
from app.tools.shared import parse_json_input, to_json_output


class CompositionEngineTool(Tool):
    name = "composition_engine"
    description = "Layer background, characters, graphics, and captions into a single frame."

    async def execute(self, input: str, *, context: Any) -> str:
        from PIL import Image

        params = parse_json_input(input)
        layers = params.get("layers")  # [{image_path, x, y, anchor?}] bottom-to-top
        out_path = params.get("output_path", "./output/composited_frame.png")
        canvas_size = tuple(params.get("canvas_size", [1080, 1920]))

        if not layers:
            raise ToolExecutionError("composition_engine requires a non-empty 'layers' array")

        canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 255))
        for i, layer in enumerate(layers):
            path = layer.get("image_path")
            if not path or not Path(path).exists():
                raise ToolExecutionError(f"Layer {i}: image_path not found: {path}")
            with Image.open(path).convert("RGBA") as img:
                x, y = layer.get("x", 0), layer.get("y", 0)
                if layer.get("anchor") == "center":
                    x -= img.width // 2
                    y -= img.height // 2
                canvas.alpha_composite(img, (int(x), int(y)))

        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        canvas.save(out_path)
        return to_json_output({"image_path": out_path, "layer_count": len(layers)})


class EffectsEngineTool(Tool):
    name = "effects_engine"
    description = "Apply lightweight parameterized effects: blur, glow, shake, vignette, motion blur, flash."

    FILTER_BUILDERS = {
        "blur": lambda p: f"boxblur={p.get('amount', 5)}",
        "vignette": lambda p: f"vignette=PI/{p.get('strength', 4)}",
        "shake": lambda p: (
            f"crop=iw-20:ih-20:10+10*sin(t*{p.get('speed', 20)}):"
            f"10+10*cos(t*{p.get('speed', 20)})"
        ),
        "flash": lambda p: f"eq=brightness={p.get('amount', 0.3)}:enable='lt(t,{p.get('duration', 0.15)})'",
    }

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        effect = params.get("effect")
        builder = self.FILTER_BUILDERS.get(effect)
        if builder is None:
            raise ToolExecutionError(f"Unknown effect '{effect}'. Known: {', '.join(self.FILTER_BUILDERS)}")

        filter_str = builder(params)
        in_path = params.get("input_path")
        out_path = params.get("output_path")

        if not in_path:
            # Spec-only mode: just return the filter graph for the caller
            # (e.g. Composition/Rendering engines) to fold into a larger
            # ffmpeg command themselves.
            return to_json_output({"effect": effect, "ffmpeg_filter": filter_str})

        if not Path(in_path).exists():
            raise ToolExecutionError(f"input_path not found: {in_path}")
        out_path = out_path or "./output/effect_output.mp4"
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)

        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", in_path, "-vf", filter_str, out_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise ToolExecutionError(f"ffmpeg effect failed: {stderr.decode(errors='replace')[-800:]}")

        return to_json_output({"effect": effect, "output_path": out_path, "ffmpeg_filter": filter_str})
