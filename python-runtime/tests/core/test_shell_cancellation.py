import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.tools.shell import ShellTool


@pytest.mark.asyncio
async def test_shell_cancellation_terminates_running_command_tree(tmp_path: Path):
    workspace = SimpleNamespace(root=tmp_path)
    context = SimpleNamespace(workspace=workspace, span_id="cancel-test")
    command = f'"{sys.executable}" -c "import time; time.sleep(1); open(\'cancel-marker.txt\', \'w\').write(\'late\')"'

    task = asyncio.create_task(ShellTool().execute(command, context=context))
    await asyncio.sleep(0.25)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=8)

    # Cancellation must finish promptly and kill descendants, not merely close
    # the Python task while a child command continues in the background.
    assert task.done()
    await asyncio.sleep(1.2)
    assert not (tmp_path / "cancel-marker.txt").exists()
