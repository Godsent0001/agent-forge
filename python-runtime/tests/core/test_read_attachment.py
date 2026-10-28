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
    (attachment_dir / "brief.txt").write_text("Project requirements\n" + ("x" * 300), encoding="utf-8")
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
    assert "\n" + ("x" * 100) + "\n[Excerpt truncated" in second.content
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


@pytest.mark.asyncio
async def test_reads_attached_python_source_as_text_without_executing_it(tmp_path: Path):
    attachment_dir = tmp_path / "attachments"
    attachment_dir.mkdir()
    source = "def add(a, b):\\n    return a + b\\n"
    (attachment_dir / "calculator.py").write_text(source, encoding="utf-8")
    tool = ReadAttachmentTool()
    ctx = SimpleNamespace(workspace=Workspace(tmp_path))

    result = await tool.run(ReadAttachmentInput(path="attachments/calculator.py"), ctx)
    assert "def add(a, b):" in result.content
    assert "return a + b" in result.content


def test_runner_marks_unscanned_attachments_as_untrusted():
    attachment = AttachmentRef(
        path="attachments/source.py", mime="text/x-python", name="source.py", scan_status="unscanned"
    )
    task = _with_attachment_context("Inspect this source", [attachment])
    assert "scan_status=\\\"unscanned\\\"" in task
    assert "do not execute or import it" in task
