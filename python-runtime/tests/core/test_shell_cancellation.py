import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.tools.shell import ShellTool


@pytest.mark.asyncio
async def test_shell_cancellation_terminates_running_command_tree(tmp_path: Path):
    workspace = SimpleNamespace(root=tmp_path)
    context = SimpleNamespace(workspace=workspace, span_id="cancel-test")
    command = f'"{sys.executable}" -c "import time; time.sleep(60)"'

    task = asyncio.create_task(ShellTool().execute(command, context=context))
    await asyncio.sleep(0.25)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=8)

    # The cancellation path must finish cleanup instead of leaving the execution
    # task blocked while subprocess pipes remain open.
    assert task.done()
