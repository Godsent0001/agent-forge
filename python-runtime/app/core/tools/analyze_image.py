"""Analyze image tool for vision-capable LLMs."""
from typing import Any, ClassVar
from pydantic import BaseModel, Field

from app.contracts.tools import Tool, ToolError, ToolResult
from app.core.llm.types import ImagePart, TextPart


class AnalyzeImageInput(BaseModel):
    path: str = Field(description="Workspace relative path to image file")
    question: str = Field(description="Question about image contents")


class AnalyzeImageTool(Tool):
    """Tool to analyze image contents using a vision model."""

    kind: ClassVar[str] = "analyze_image"
    default_description: ClassVar[str] = "Analyze an image using a vision model."
    Input: ClassVar[type[BaseModel]] = AnalyzeImageInput

    def __init__(self, vision_llm_complete_fn: Any = None):
        self.vision_llm_complete_fn = vision_llm_complete_fn

    async def run(self, args: AnalyzeImageInput, ctx: Any) -> ToolResult:
        if not hasattr(ctx, "workspace") or not ctx.workspace:
            raise ToolError("Workspace context unavailable.")

        try:
            target_path = ctx.workspace.resolve(args.path)
            if not target_path.is_file():
                raise ToolError(f"Image file not found: '{args.path}'")

            rel_path = ctx.workspace.relative(target_path)
            mime = "image/png" if rel_path.endswith(".png") else "image/jpeg"
        except ToolError:
            raise
        except Exception as e:
            raise ToolError(f"Image file error: {e}")

        if not self.vision_llm_complete_fn:
            return ToolResult(
                ok=True,
                content=f"Vision model unconfigured. Image '{args.path}' received question '{args.question}'.",
            )

        msg_content = [
            ImagePart(path=rel_path, mime=mime).model_dump(),
            TextPart(text=args.question).model_dump(),
        ]

        try:
            turn = await self.vision_llm_complete_fn([{"role": "user", "content": msg_content}])
            return ToolResult(ok=True, content=turn.text or "Image analysis complete.")
        except Exception as e:
            raise ToolError(f"Vision model call failed: {e}")
