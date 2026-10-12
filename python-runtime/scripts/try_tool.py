"""Run a legacy-backed v2 tool without launching Electron or the LLM.

Example (from python-runtime):
    uv run python scripts/try_tool.py http_request '{"input":"GET https://example.com"}'
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.contracts.graph import ToolBinding  # noqa: E402
from app.contracts.tools import ToolError  # noqa: E402
from app.services.core_adapters import Workspace  # noqa: E402
from app.tools.registry import DefaultToolFactory  # noqa: E402


class _Cancel:
    cancelled = False

    def raise_if_cancelled(self):
        if self.cancelled:
            raise asyncio.CancelledError


class _Context:
    def __init__(self, execution_id: str, workspace: Workspace, config: dict):
        self.execution_id = execution_id
        self.span_id = str(uuid4())
        self.workspace = workspace
        self.cancel = _Cancel()
        self.config = config
        self.agent_id = "cli"


async def run_tool(kind: str, raw_args: str) -> int:
    try:
        values = json.loads(raw_args)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON arguments: {exc}", file=sys.stderr)
        return 2
    if not isinstance(values, dict):
        print("Arguments must be a JSON object.", file=sys.stderr)
        return 2

    execution_id = str(uuid4())
    binding = ToolBinding(
        id=str(uuid4()), kind=kind, name=kind, config={},
    )
    workspace = Workspace(execution_id)
    try:
        tool = DefaultToolFactory().build(binding)
        parsed = tool.Input.model_validate(values)
        result = await tool.run(parsed, _Context(execution_id, workspace, binding.config))
        print(result.model_dump_json(indent=2))
        return 0 if result.ok else 1
    except (ValueError, ToolError) as exc:
        print(f"Tool failed: {exc}", file=sys.stderr)
        return 1
    finally:
        workspace.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", help="Registered tool kind, e.g. http_request or python")
    parser.add_argument("args", help='JSON object for the tool, e.g. \'{"input":"GET https://example.com"}\'')
    parsed = parser.parse_args()
    return asyncio.run(run_tool(parsed.kind, parsed.args))


if __name__ == "__main__":
    raise SystemExit(main())
