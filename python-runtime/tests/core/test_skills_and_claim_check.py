import pytest
from pathlib import Path
import tempfile
from app.core.skills.parser import parse_skill_markdown
from app.core.claim_check import TaskDirective, ClaimCheckEnvelope, ClaimCheckSummary
from app.core.workspace_cleanup import cleanup_ephemeral_artifacts


def test_skill_manifest_parsing():
    content = """---
name: code_reviewer
description: "Reviews code for security issues."
metadata:
  tools:
    - doc_search
    - file_system
---

# Code Review Operational Runbook
1. Check input files using doc_search.
2. Highlight security issues.
"""
    manifest = parse_skill_markdown(content)
    assert manifest.name == "code_reviewer"
    assert manifest.metadata.tools == ["doc_search", "file_system"]
    assert "Code Review Operational Runbook" in manifest.runbook_markdown


def test_claim_check_envelopes():
    directive = TaskDirective(
        task_id="task_1",
        sender_id="ceo",
        recipient_id="analyst",
        instruction="Analyze Q3 growth",
    )
    assert directive.task_id == "task_1"

    envelope = ClaimCheckEnvelope(
        task_id="task_1",
        sender_id="analyst",
        recipient_id="ceo",
        status="COMPLETED",
        summary=ClaimCheckSummary(headline="Q3 growth was 15%"),
        result_artifact_uri="store://.results/task_1.txt",
    )
    data = envelope.model_dump_json()
    assert "Q3 growth was 15%" in data
    assert "store://.results/task_1.txt" in data


def test_workspace_artifact_cleanup():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        res_dir = root / ".results"
        res_dir.mkdir(parents=True)

        old_file = res_dir / "old.txt"
        old_file.write_text("old result")

        # Cleanup with 0 second max age
        deleted = cleanup_ephemeral_artifacts(root, max_age_seconds=0)
        assert deleted == 1
        assert not old_file.exists()
