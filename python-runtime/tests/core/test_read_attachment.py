from pathlib import Path
from types import SimpleNamespace

import pytest

from app.contracts.run import AttachmentRef
from app.contracts.tools import ToolError
from app.core.runner import _with_attachment_context
from app.core.tools.read_attachment import ReadAttachmentInput, ReadAttachmentTool


class Workspace:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def resolve(self, relative: str) -> Path:
        candidate = (self.root / relative).resolve()
        if not candidate.is_relative_to(self.root):
            raise ValueError("path escaped workspace")
        return candidate


@pytest.mark.asyncio
async def test_reads_text_attachment_in_bounded_chunks(tmp_path: Path):
    attachment_dir = tmp_path / "attachments"
    attachment_dir.mkdir()
    (attachment_dir / "brief.txt").write_text("Project requirements\n + ("x" * 300), encoding="utf-8")
    tool = ReadAttachmentTool()
    ctx = SimpleNamespace(workspace=Workspace(tmp_path))

    first = await tool.run(
        ReadAttachmentInput(path="attachments/brief.txt", max_chars=100),
        ctx,
    )
    assert "Project requirements" in first.content
    assert first.truncated is True
    assert first.next_offset == 100

    second = await tool.run(
        ReadAttachmentInput(path="attachments/brief.txt", start_char=first.next_offset, max_chars=100),
        ctx,
    )
    assert second.content.endswith("x" * 100)
    assert second.truncated is True


@pytest.mark.asyncio
async def test_reader_rejects_paths_outside_attachment_directory(tmp_path: Path):
    tool = ReadAttachmentTool()
    ctx = SimpleNamespace(workspace=Workspace(tmp_path))
    with pytest.raises(ToolError, match="run-private attachment"):
        await tool.run(ReadAttachmentInput(path="../secret.txt"), ctx)


@pytest.mark.asyncio
async def test_reader_rejects_non_text_attachments(tmp_path: Path):
    tool = ReadAttachmentTool()
    ctx = SimpleNamespace(workspace=Workspace(tmp_path))
    with pytest.raises(ToolError, match="supports only"):
        await tool.run(ReadAttachmentInput(path="attachments/clip.mp4"), ctx)


def test_runner_adds_attachment_manifest_and_safe_read_guidance():
    attachment = AttachmentRef(path="attachments/abc123.txt", mime="text/plain", name="brief.txt")
    task = _with_attachment_context("Summarize this brief", [attachment])
    assert "Summarize this brief" in task
    assert "attachments/abc123.txt" in task
    assert "read_attachment" in task
    assert "untrusted user-provided data" in task
    assert _with_attachment_context(task, [attachment]) == task
