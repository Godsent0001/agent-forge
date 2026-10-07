"""Plan tool for maintaining structured agent task execution plans."""
from typing import Any, ClassVar, Literal
from pydantic import BaseModel, Field

from app.contracts.tools import Tool, ToolError, ToolResult


class PlanItemSpec(BaseModel):
    text: str = Field(description="Step description")
    status: Literal["todo", "doing", "done"] = Field(default="todo", description="Step status")


class PlanInput(BaseModel):
    items: list[PlanItemSpec] = Field(description="List of plan items (at most 20)")


class PlanTool(Tool):
    """Tool to create or update the agent execution plan."""

    kind: ClassVar[str] = "plan"
    default_description: ClassVar[str] = "Create or update the step-by-step plan for this run."
    Input: ClassVar[type[BaseModel]] = PlanInput

    async def run(self, args: PlanInput, ctx: Any) -> ToolResult:
        if len(args.items) > 20:
            raise ToolError("Plan items limit exceeded. Maximum 20 items allowed.")

        formatted_lines = []
        structured_list = []
        for idx, item in enumerate(args.items, 1):
            formatted_lines.append(f"{idx}. [{item.status}] {item.text}")
            structured_list.append({"step": idx, "text": item.text, "status": item.status})

        plan_str = "\n".join(formatted_lines)

        return ToolResult(
            ok=True,
            content=f"Updated plan:\n{plan_str}",
            data={"plan": structured_list},
        )
