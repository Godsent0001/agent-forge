from __future__ import annotations

import json

from app.services import conversation_backfill


def test_fact_files_keep_only_batch_grounded_facts_and_are_discoverable(tmp_path, monkeypatch):
    monkeypatch.setattr(
        conversation_backfill,
        "project_dir",
        lambda project_id: tmp_path / project_id,
    )
    written = conversation_backfill._store_groups(
        "project-1",
        "conversation-1",
        [{
            "file_id": "cloudflare-vps",
            "title": "VPS and Cloudflare configuration",
            "description": "VPS connection details, Cloudflare DNS records and deployment configuration.",
            "facts": [
                {
                    "text": "The SSH port is 2222.",
                    "source_message_ids": ["message-1"],
                },
                {
                    "text": "Unverified invented value.",
                    "source_message_ids": ["message-outside-batch"],
                },
            ],
        }],
        {"message-1"},
    )

    assert written == 1
    descriptions = conversation_backfill.list_fact_descriptions("project-1", "conversation-1")
    assert descriptions == [{
        "id": "cloudflare-vps",
        "title": "VPS and Cloudflare configuration",
        "description": "VPS connection details, Cloudflare DNS records and deployment configuration.",
    }]
    loaded = conversation_backfill.load_fact_file(
        "project-1", "conversation-1", "cloudflare-vps"
    )
    assert loaded is not None
    assert loaded["facts"] == [{
        "source_message_id": "message-1",
        "text": "The SSH port is 2222.",
    }]
    assert conversation_backfill.load_fact_file(
        "project-1", "conversation-1", "../outside"
    ) is None


def test_fact_file_updates_are_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(
        conversation_backfill,
        "project_dir",
        lambda project_id: tmp_path / project_id,
    )
    group = {
        "file_id": "architecture",
        "title": "Architecture decisions",
        "description": "Accepted architecture choices and their rationale.",
        "facts": [{
            "text": "Use SQLite for durable task state.",
            "source_message_ids": ["message-1"],
        }],
    }
    conversation_backfill._store_groups(
        "project-1", "conversation-1", [group], {"message-1"}
    )
    conversation_backfill._store_groups(
        "project-1", "conversation-1", [group], {"message-1"}
    )
    loaded = conversation_backfill.load_fact_file(
        "project-1", "conversation-1", "architecture"
    )
    assert loaded is not None
    assert len(loaded["facts"]) == 1
