"""
Graphics shelf. These render actual pixels via PIL/matplotlib — real
output, not instruction JSON, since 2D graphics don't need a character
rig or GPU renderer the way the Character shelf does.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.tools.base import Tool, ToolExecutionError
from app.tools.shared import parse_json_input, to_json_output

VIDEO_W, VIDEO_H = 1080, 1920  # vertical short-form, per Final Renderer spec


def _font(size: int):
    from PIL import ImageFont
    # Falls back to PIL's bundled default bitmap font if no system TTF is
    # found — output will look plain but the tool still produces a valid
    # image rather than failing outright.
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


import json
import re


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[-\s]+", "_", text)


class PropDesignerTool(Tool):
    name = "prop_designer"
    description = "Create reusable visual prop assets (podium, microphone, chair, desk, table, lectern, TV screen, books, debate timer)."

    def __init__(self, props_dir: str = "./assets/props"):
        self._root = Path(props_dir)

    async def execute(self, input: str, *, context: Any) -> str:
        from PIL import Image, ImageDraw

        params = parse_json_input(input)
        name = params.get("name") or "Podium"
        prop_id = params.get("prop_id") or params.get("id") or _slugify(name)
        kind = params.get("kind") or params.get("type") or "podium"
        desc = params.get("description", "")
        material = params.get("material", "wood")

        prop_dir = self._root / prop_id
        prop_dir.mkdir(parents=True, exist_ok=True)

        metadata = {
            "prop_id": prop_id,
            "name": name,
            "kind": kind,
            "material": material,
            "description": desc,
        }

        meta_path = prop_dir / "metadata.json"
        meta_path.write_text(json.dumps(metadata, indent=2))

        asset_path = str(prop_dir / "asset.png")
        w, h = 600, 600
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Draw prop graphic based on kind
        if kind in ["podium", "lectern"]:
            draw.polygon([(180, 200), (420, 200), (380, 520), (220, 520)], fill=(69, 26, 3, 255), outline=(217, 119, 6, 255), width=4)
            draw.rectangle([150, 170, 450, 200], fill=(120, 53, 15, 255))
        elif kind == "microphone":
            draw.rectangle([285, 250, 315, 480], fill=(71, 85, 105, 255))
            draw.ellipse([270, 180, 330, 250], fill=(148, 163, 184, 255))
            draw.ellipse([240, 480, 360, 520], fill=(30, 41, 59, 255))
        elif kind in ["tv_screen", "timer", "debate_timer"]:
            draw.rectangle([100, 150, 500, 450], fill=(15, 23, 42, 255), outline=(99, 102, 241, 255), width=6)
            draw.text((w // 2, h // 2), "00:00", font=_font(48), fill=(239, 68, 68, 255), anchor="mm")
        else:
            draw.rectangle([150, 200, 450, 480], fill=(51, 65, 85, 255), outline=(203, 213, 225, 255), width=4)

        draw.text((w // 2, 80), name, font=_font(28), fill=(255, 255, 255, 255), anchor="mm")

        img.save(asset_path)

        return to_json_output({
            "prop_id": prop_id,
            "name": name,
            "kind": kind,
            "metadata_path": str(meta_path),
            "asset_path": asset_path,
            "status": "created",
        })


class VisualAssetManagerTool(Tool):
    name = "visual_asset_manager"
    description = "Manage and retrieve visual assets across characters, environments, props, and graphics by ID."

    def __init__(self, assets_dir: str = "./assets"):
        self._root = Path(assets_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    async def execute(self, input: str, *, context: Any) -> str:
        from PIL import Image

        params = parse_json_input(input)
        action = params.get("action", "list")
        asset_id = params.get("asset_id") or params.get("id") or params.get("name")

        if action in ["list", "list_assets"]:
            category = params.get("category")  # characters | environments | props | visuals
            results = {}

            categories = ["characters", "environments", "props", "visuals"]
            if category and category in categories:
                categories = [category]

            for cat in categories:
                cat_dir = self._root / cat
                cat_items = []
                if cat_dir.exists():
                    for p in cat_dir.iterdir():
                        if p.is_dir():
                            cat_items.append(p.name)
                        elif p.is_file():
                            cat_items.append(p.name)
                results[cat] = cat_items

            return to_json_output({"assets": results})

        if action in ["get", "info"]:
            if not asset_id:
                raise ToolExecutionError("visual_asset_manager 'get' requires 'asset_id' or 'name'")

            # Search in characters, environments, props, visuals
            for cat in ["characters", "environments", "props", "visuals"]:
                target_dir = self._root / cat / asset_id
                if target_dir.exists() and target_dir.is_dir():
                    meta_file = target_dir / "metadata.json"
                    if not meta_file.exists():
                        meta_file = target_dir / "profile.json"

                    metadata = json.loads(meta_file.read_text()) if meta_file.exists() else {}
                    asset_file = target_dir / "asset.png"
                    if not asset_file.exists():
                        asset_file = target_dir / "preview.png"

                    return to_json_output({
                        "asset_id": asset_id,
                        "category": cat,
                        "metadata": metadata,
                        "asset_path": str(asset_file) if asset_file.exists() else None,
                        "directory": str(target_dir),
                    })

                # Check direct file in visuals
                file_path = self._root / cat / asset_id
                if file_path.exists() and file_path.is_file():
                    with Image.open(file_path) as img:
                        return to_json_output({
                            "asset_id": asset_id,
                            "category": cat,
                            "path": str(file_path),
                            "size": img.size,
                            "format": img.format,
                        })

            raise ToolExecutionError(f"No asset found matching '{asset_id}'.")

        raise ToolExecutionError(f"Unknown action '{action}'. Use list or get.")


class EvidenceGraphicsTool(Tool):
    name = "evidence_graphics"
    description = "Render an evidence card image (stat + claim + source) as a PNG."

    async def execute(self, input: str, *, context: Any) -> str:
        from PIL import Image, ImageDraw

        params = parse_json_input(input)
        stat = params.get("stat", "")
        claim = params.get("claim", "")
        source = params.get("source", "")
        out_path = params.get("output_path", "./output/evidence_card.png")
        if not stat and not claim:
            raise ToolExecutionError("evidence_graphics requires at least 'stat' or 'claim'")

        w, h = 900, 500
        img = Image.new("RGBA", (w, h), (17, 17, 21, 255))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, w - 1, h - 1], outline=(99, 102, 241, 255), width=4)
        draw.text((w / 2, 60), "EVIDENCE", font=_font(28), fill=(165, 180, 252, 255), anchor="mm")
        if stat:
            draw.text((w / 2, h / 2 - 30), stat, font=_font(72), fill=(255, 255, 255, 255), anchor="mm")
        draw.text((w / 2, h / 2 + 60), claim, font=_font(26), fill=(200, 200, 205, 255), anchor="mm")
        if source:
            draw.text((w / 2, h - 40), f"Source: {source}", font=_font(18), fill=(120, 120, 130, 255), anchor="mm")

        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path)
        return to_json_output({"image_path": out_path, "width": w, "height": h})


class DataVisualizationTool(Tool):
    name = "data_visualization"
    description = "Generate bar/line/comparison charts from structured data."

    async def execute(self, input: str, *, context: Any) -> str:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        params = parse_json_input(input)
        chart_type = params.get("chart_type", "bar")
        labels = params.get("labels")
        values = params.get("values")
        out_path = params.get("output_path", "./output/chart.png")
        title = params.get("title", "")

        if not labels or not values or len(labels) != len(values):
            raise ToolExecutionError("data_visualization requires equal-length 'labels' and 'values'")

        fig, ax = plt.subplots(figsize=(8, 5), facecolor="#111115")
        ax.set_facecolor("#111115")
        accent = "#6366f1"

        if chart_type == "bar":
            ax.bar(labels, values, color=accent)
        elif chart_type == "line":
            ax.plot(labels, values, color=accent, marker="o", linewidth=2)
        elif chart_type == "comparison" and len(values) == 2 and isinstance(values[0], (int, float)):
            ax.barh(labels[:2], values[:2], color=[accent, "#a5b4fc"])
        else:
            raise ToolExecutionError(f"Unknown or malformed chart_type '{chart_type}'")

        ax.set_title(title, color="white")
        ax.tick_params(colors="white")
        for spine in ax.spines.values():
            spine.set_color("#333340")

        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, facecolor=fig.get_facecolor(), dpi=150, bbox_inches="tight")
        plt.close(fig)

        return to_json_output({"image_path": out_path, "chart_type": chart_type})


class HeadlineCardTool(Tool):
    name = "headline_card"
    description = "Render stylized BREAKING / REPORT / STUDY / COURT RULING cards."

    KINDS = {"BREAKING", "REPORT", "STUDY", "MARKET UPDATE", "COURT RULING"}

    async def execute(self, input: str, *, context: Any) -> str:
        from PIL import Image, ImageDraw

        params = parse_json_input(input)
        kind = params.get("kind", "REPORT").upper()
        headline = params.get("headline", "")
        out_path = params.get("output_path", "./output/headline_card.png")
        if kind not in self.KINDS:
            raise ToolExecutionError(f"Unknown kind '{kind}'. Known: {', '.join(self.KINDS)}")
        if not headline:
            raise ToolExecutionError("headline_card requires 'headline'")

        w, h = 1000, 260
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, 220, 60], fill=(239, 68, 68, 255))
        draw.text((110, 30), kind, font=_font(24), fill=(255, 255, 255, 255), anchor="mm")
        draw.text((20, 100), headline, font=_font(42), fill=(255, 255, 255, 255), anchor="lm")

        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path)
        return to_json_output({"image_path": out_path, "kind": kind})


class DebateGraphicsTool(Tool):
    name = "debate_graphics"
    description = "Render franchise labels: CLAIM, COUNTER, EVIDENCE, REBUTTAL, TRAP, CONCESSION, etc."

    LABELS = {
        "CLAIM": (99, 102, 241), "COUNTER": (245, 158, 11), "EVIDENCE": (16, 185, 129),
        "REBUTTAL": (239, 68, 68), "TRAP": (239, 68, 68), "CONCESSION": (16, 185, 129),
        "PERSPECTIVE FLIP": (165, 180, 252), "FINAL QUESTION": (255, 255, 255),
    }

    async def execute(self, input: str, *, context: Any) -> str:
        from PIL import Image, ImageDraw

        params = parse_json_input(input)
        label = params.get("label", "").upper()
        out_path = params.get("output_path", "./output/debate_label.png")
        color = self.LABELS.get(label)
        if color is None:
            raise ToolExecutionError(f"Unknown label '{label}'. Known: {', '.join(self.LABELS)}")

        w, h = 400, 90
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([0, 0, w - 1, h - 1], radius=12, fill=(*color, 255))
        draw.text((w / 2, h / 2), label, font=_font(30), fill=(255, 255, 255, 255), anchor="mm")

        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path)
        return to_json_output({"image_path": out_path, "label": label})


class CaptionEngineTool(Tool):
    name = "caption_engine"
    description = "Generate timed captions/subtitles (SRT) from alignment data."

    async def execute(self, input: str, *, context: Any) -> str:
        params = parse_json_input(input)
        words = params.get("words")  # from audio_alignment
        max_words_per_line = params.get("max_words_per_line", 5)
        out_path = params.get("output_path", "./output/captions.srt")

        if not words:
            raise ToolExecutionError("caption_engine requires a 'words' array (from audio_alignment output)")

        def fmt_ts(seconds: float) -> str:
            ms = int(round(seconds * 1000))
            h, ms = divmod(ms, 3_600_000)
            m, ms = divmod(ms, 60_000)
            s, ms = divmod(ms, 1000)
            return f"{h:02}:{m:02}:{s:02},{ms:03}"

        chunks = [words[i:i + max_words_per_line] for i in range(0, len(words), max_words_per_line)]
        lines = []
        for i, chunk in enumerate(chunks, start=1):
            start, end = chunk[0]["start"], chunk[-1]["end"]
            text = " ".join(w["text"] for w in chunk)
            lines.append(f"{i}\n{fmt_ts(start)} --> {fmt_ts(end)}\n{text}\n")

        srt = "\n".join(lines)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(srt)

        return to_json_output({"srt_path": out_path, "line_count": len(chunks)})


class TypographyEngineTool(Tool):
    name = "typography_engine"
    description = "Render large on-screen text elements with hierarchy and styling."

    async def execute(self, input: str, *, context: Any) -> str:
        from PIL import Image, ImageDraw

        params = parse_json_input(input)
        text = params.get("text", "")
        size = params.get("size", 64)
        out_path = params.get("output_path", "./output/typography.png")
        if not text:
            raise ToolExecutionError("typography_engine requires 'text'")

        font = _font(size)
        dummy = Image.new("RGBA", (1, 1))
        bbox = ImageDraw.Draw(dummy).textbbox((0, 0), text, font=font)
        w, h = bbox[2] - bbox[0] + 40, bbox[3] - bbox[1] + 40

        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.text((w / 2, h / 2), text, font=font, fill=(255, 255, 255, 255), anchor="mm")

        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path)
        return to_json_output({"image_path": out_path, "width": w, "height": h})
