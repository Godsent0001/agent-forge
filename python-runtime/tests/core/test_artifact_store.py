import hashlib

import pytest

from app.contracts.artifacts import ArtifactCreate, ArtifactUpdate
from app.core.artifact_store import (
    ArtifactNotFound,
    ArtifactVersionConflict,
    InvalidArtifactDependency,
    SQLiteArtifactStore,
)


def spec(project_id="project-1", name="asset.bin", artifact_type="binary", dependencies=None):
    return ArtifactCreate(
        project_id=project_id,
        artifact_type=artifact_type,
        name=name,
        dependencies=dependencies or [],
    )


def test_create_read_and_version_history_are_immutable(tmp_path):
    store = SQLiteArtifactStore(tmp_path)
    original = b"original payload"
    record = store.create(spec(), original, actor="test")

    assert record.version == 1
    assert record.sha256 == hashlib.sha256(original).hexdigest()
    assert store.read(record.artifact_id).content == original

    updated = store.update(
        record.artifact_id,
        b"edited payload",
        ArtifactUpdate(expected_version=1, change_summary="Edit one region"),
        actor="test",
    )
    assert updated.version == 2
    assert store.read(record.artifact_id).content == b"edited payload"
    assert store.read(record.artifact_id, version=1).content == original
    assert [v.version for v in store.history(record.artifact_id)] == [1, 2]
    assert store.changes(record.artifact_id)[0].summary == "Edit one region"


def test_stale_update_is_rejected_without_creating_a_version(tmp_path):
    store = SQLiteArtifactStore(tmp_path)
    record = store.create(spec(), b"v1")
    store.update(record.artifact_id, b"v2", ArtifactUpdate(expected_version=1, change_summary="v2"))

    with pytest.raises(ArtifactVersionConflict):
        store.update(record.artifact_id, b"lost update", ArtifactUpdate(expected_version=1, change_summary="stale"))

    assert store.get(record.artifact_id).version == 2
    assert len(store.history(record.artifact_id)) == 2


def test_dependency_must_exist_and_belong_to_same_project(tmp_path):
    store = SQLiteArtifactStore(tmp_path)
    foreign = store.create(spec(project_id="other-project"), b"foreign")

    with pytest.raises(InvalidArtifactDependency):
        store.create(spec(dependencies=[foreign.artifact_id]), b"invalid")

    with pytest.raises(InvalidArtifactDependency):
        store.create(spec(dependencies=["missing-artifact"]), b"invalid")


def test_dependency_cycles_are_rejected(tmp_path):
    store = SQLiteArtifactStore(tmp_path)
    first = store.create(spec(name="first"), b"1")
    second = store.create(spec(name="second", dependencies=[first.artifact_id]), b"2")

    with pytest.raises(InvalidArtifactDependency):
        store.update(
            first.artifact_id,
            b"new first",
            ArtifactUpdate(
                expected_version=1,
                change_summary="Would create a cycle",
                dependencies=[second.artifact_id],
            ),
        )


def test_project_listing_is_scoped_and_integrity_is_checked(tmp_path):
    store = SQLiteArtifactStore(tmp_path)
    one = store.create(spec(project_id="p1", name="one"), b"1")
    store.create(spec(project_id="p2", name="two"), b"2")

    assert [item.artifact_id for item in store.list_project("p1")] == [one.artifact_id]
    assert store.verify_integrity(one.artifact_id)

    blob = store._blob_path(one.sha256)
    blob.write_bytes(b"tampered")
    assert not store.verify_integrity(one.artifact_id)
    with pytest.raises(Exception, match="integrity check failed"):
        store.read(one.artifact_id)


def test_unknown_artifact_update_is_reported(tmp_path):
    store = SQLiteArtifactStore(tmp_path)
    with pytest.raises(ArtifactNotFound):
        store.update(
            "missing",
            b"x",
            ArtifactUpdate(expected_version=1, change_summary="not found"),
        )
