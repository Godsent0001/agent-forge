import pytest

from app.contracts.artifacts import ArtifactCreate
from app.contracts.verification import VerificationCheck, VerificationReport
from app.core.artifact_store import SQLiteArtifactStore
from app.core.verification import VerificationEngine


@pytest.mark.asyncio
async def test_missing_verifier_is_not_treated_as_success(tmp_path):
    store = SQLiteArtifactStore(tmp_path)
    record = store.create(ArtifactCreate(project_id="p", artifact_type="video", name="clip"), b"video bytes")
    report = await VerificationEngine().verify(store.read(record.artifact_id))
    assert report.status == "skipped"
    assert report.artifact_version == 1


@pytest.mark.asyncio
async def test_verifier_pass_and_identity_are_enforced(tmp_path):
    store = SQLiteArtifactStore(tmp_path)
    record = store.create(ArtifactCreate(project_id="p", artifact_type="image", name="image"), b"image bytes")

    class GoodVerifier:
        name = "image-check"
        async def verify(self, artifact, context):
            assert context["profile"] == "strict"
            return VerificationReport(
                artifact_id=artifact.record.artifact_id,
                artifact_version=artifact.record.version,
                status="passed",
                checks=[VerificationCheck(check_id="decode", status="passed", summary="Decoded")],
            )

    engine = VerificationEngine()
    engine.register("image", GoodVerifier())
    report = await engine.verify(store.read(record.artifact_id), context={"profile": "strict"})
    assert report.status == "passed"
    assert report.verifier == "image-check"

    class WrongIdentity:
        name = "bad-identity"
        async def verify(self, artifact, context):
            return VerificationReport(artifact_id="another-artifact", artifact_version=1, status="passed")

    other = VerificationEngine()
    other.register("image", WrongIdentity())
    report = await other.verify(store.read(record.artifact_id))
    assert report.status == "failed"
    assert report.checks[0].check_id == "verification_identity"


@pytest.mark.asyncio
async def test_failed_checks_and_warnings_cannot_be_reported_as_passed(tmp_path):
    store = SQLiteArtifactStore(tmp_path)
    record = store.create(ArtifactCreate(project_id="p", artifact_type="data", name="data"), b"payload")

    class WarningVerifier:
        name = "warning-check"
        async def verify(self, artifact, context):
            return VerificationReport(
                artifact_id=artifact.record.artifact_id,
                artifact_version=artifact.record.version,
                status="passed",
                checks=[VerificationCheck(check_id="schema", status="warning", summary="Partial validation")],
            )

    engine = VerificationEngine()
    engine.register("data", WarningVerifier())
    report = await engine.verify(store.read(record.artifact_id))
    assert report.status == "needs_review"

    class FailedVerifier:
        name = "failed-check"
        async def verify(self, artifact, context):
            return VerificationReport(
                artifact_id=artifact.record.artifact_id,
                artifact_version=artifact.record.version,
                status="passed",
                checks=[VerificationCheck(check_id="schema", status="failed", summary="Invalid schema")],
            )

    engine = VerificationEngine()
    engine.register("data", FailedVerifier())
    report = await engine.verify(store.read(record.artifact_id))
    assert report.status == "failed"


@pytest.mark.asyncio
async def test_verifier_exception_fails_closed(tmp_path):
    store = SQLiteArtifactStore(tmp_path)
    record = store.create(ArtifactCreate(project_id="p", artifact_type="code", name="src.py"), b"print(1)")

    class CrashingVerifier:
        name = "crash-check"
        async def verify(self, artifact, context):
            raise RuntimeError("may contain sensitive details")

    engine = VerificationEngine()
    engine.register("code", CrashingVerifier())
    report = await engine.verify(store.read(record.artifact_id))
    assert report.status == "failed"
    assert report.checks[0].details == {"error_type": "RuntimeError"}
