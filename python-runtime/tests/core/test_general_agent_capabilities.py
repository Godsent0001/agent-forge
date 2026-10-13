from __future__ import annotations

import asyncio
import hashlib

import pytest

from app.core.capabilities import (
    CapabilityDenied, CapabilityRegistry, CapabilityResult, CapabilitySpec,
)
from app.core.knowledge import KnowledgeIndex, extract_document
from app.core.longform import LongFormWorkflow, SectionSpec
from app.core.safe_editing import (
    EditConflict, EditValidationError, SafeWorkspaceEditor, TextReplacement,
)


def test_knowledge_ingestion_replacement_and_hybrid_search(tmp_path):
    index = KnowledgeIndex(tmp_path / "knowledge.sqlite3")
    first = extract_document("research.txt", b"Quantum systems use entanglement and quantum states.\n" * 12)
    assert index.ingest(first, chunk_chars=120, overlap_chars=20) >= 1
    assert index.search("entanglement")
    assert index.ingest(extract_document("research.txt", b"New material discusses orbital mechanics."), chunk_chars=120, overlap_chars=20) == 1
    assert "orbital" in index.search("orbital")[0].chunk.text
    assert not index.search("entanglement")

    semantic_doc = extract_document("other.txt", b"Totally different words about deep ocean exploration.")
    index.ingest(semantic_doc)
    hits = index.search("submarine abyss", semantic_score=lambda q, text: 0.99 if "ocean" in text else 0.1)
    assert hits and hits[0].chunk.source_name == "other.txt"


def test_safe_editing_preview_conflict_and_rollback(tmp_path):
    (tmp_path / "notes.md").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    editor = SafeWorkspaceEditor(tmp_path)
    original, digest = editor.read("notes.md")
    preview, proposed = editor.preview_replacements(
        "notes.md", [TextReplacement("beta", "BETA")], expected_sha256=digest
    )
    assert preview.changed and "-beta" in preview.unified_diff and "+BETA" in preview.unified_diff
    edit = editor.apply("notes.md", proposed, expected_sha256=digest, reason="test targeted edit")
    assert (tmp_path / "notes.md").read_text(encoding="utf-8") == "alpha\nBETA\ngamma\n"
    with pytest.raises(EditConflict):
        editor.apply("notes.md", b"unsafe overwrite", expected_sha256=digest)
    current, current_hash = editor.read("notes.md")
    editor.rollback(edit.edit_id, expected_current_sha256=current_hash)
    assert (tmp_path / "notes.md").read_bytes() == original
    with pytest.raises(EditValidationError):
        editor.read("../outside.txt")


def test_safe_editing_requires_unambiguous_target(tmp_path):
    (tmp_path / "dup.txt").write_text("x x x", encoding="utf-8")
    editor = SafeWorkspaceEditor(tmp_path)
    _, digest = editor.read("dup.txt")
    with pytest.raises(EditConflict):
        editor.preview_replacements("dup.txt", [TextReplacement("x", "y")], expected_sha256=digest)


def test_longform_checkpoints_resume_and_verify(tmp_path):
    workflow = LongFormWorkflow(tmp_path / "longform.sqlite3")
    sections = [
        SectionSpec("intro", "Introduction", "Explain the problem.", ("state the problem",)),
        SectionSpec("solution", "Solution", "Describe a practical solution."),
    ]
    pid = workflow.create_project("Test project", sections, project_id="project-1")
    calls = []

    async def generator(title, section, context, previous_summaries):
        calls.append(section.section_id)
        return f"{section.title}: a detailed and verified explanation."

    async def verifier(section, content):
        return ("verified" in content.casefold(), "must contain verified")

    result = asyncio.run(workflow.run(pid, generator=generator, verifier=verifier))
    assert result.word_count > 0 and len(result.sections) == 2
    assert workflow.get_status(pid)["status"] == "completed"
    assert calls == ["intro", "solution"]

    calls.clear()
    resumed = asyncio.run(workflow.run(pid, generator=generator, verifier=verifier))
    assert resumed.sha256 == result.sha256
    assert calls == []
    assert all(s.reused_checkpoint for s in resumed.sections)


def test_capability_registry_enforces_policy_and_normalizes_result():
    registry = CapabilityRegistry(permission_policy=lambda spec, args, ctx: args.get("approved") is True)

    class Adapter:
        async def execute(self, arguments, context):
            return CapabilityResult(capability="wrong-name", ok=True, content="done", retryable=True)

    registry.register(CapabilitySpec(
        name="analyze", domain="research", description="Analyze content", idempotent=False,
        timeout_seconds=2,
    ), Adapter())

    async def run():
        with pytest.raises(CapabilityDenied):
            await registry.execute("analyze", {"approved": False})
        result = await registry.execute("analyze", {"approved": True})
        assert result.ok and result.capability == "analyze" and not result.retryable

    asyncio.run(run())
