"""Verification orchestration shared by all artifact modalities."""
from __future__ import annotations

import inspect
import logging
from typing import Any

from app.contracts.artifacts import ArtifactPayload
from app.contracts.verification import VerificationCheck, VerificationReport

logger = logging.getLogger(__name__)


class VerificationEngine:
    """Dispatch to registered type-specific verifiers and normalize outcomes.

    No registered verifier is reported as 'skipped', never as a successful check.
    Verifiers are read-only by contract; changes must go through ArtifactStore.update.
    """

    def __init__(self) -> None:
        self._verifiers: dict[str, Any] = {}

    def register(self, artifact_type: str, verifier: Any) -> None:
        key = artifact_type.strip().casefold()
        if not key:
            raise ValueError("artifact_type must not be blank.")
        if key in self._verifiers:
            raise ValueError(f"A verifier is already registered for artifact type {artifact_type!r}.")
        if not callable(getattr(verifier, "verify", None)):
            raise TypeError("Verifier must provide verify(artifact, context).")
        self._verifiers[key] = verifier

    def supports(self, artifact_type: str) -> bool:
        return artifact_type.strip().casefold() in self._verifiers

    async def verify(
        self,
        artifact: ArtifactPayload,
        *,
        context: dict[str, Any] | None = None,
    ) -> VerificationReport:
        key = artifact.record.artifact_type.strip().casefold()
        verifier = self._verifiers.get(key)
        if verifier is None:
            return VerificationReport(
                artifact_id=artifact.record.artifact_id,
                artifact_version=artifact.record.version,
                status="skipped",
                summary=f"No verifier registered for artifact type '{artifact.record.artifact_type}'.",
                verifier="none",
            )

        verifier_name = str(getattr(verifier, "name", type(verifier).__name__))[:200]
        try:
            result = verifier.verify(artifact, context or {})
            if inspect.isawaitable(result):
                result = await result
            if not isinstance(result, VerificationReport):
                raise TypeError("Verifier must return VerificationReport.")
        except Exception as exc:
            logger.exception("Artifact verifier %s failed", verifier_name)
            return VerificationReport(
                artifact_id=artifact.record.artifact_id,
                artifact_version=artifact.record.version,
                status="failed",
                summary="Verifier raised an exception; output was not verified.",
                verifier=verifier_name,
                checks=[VerificationCheck(
                    check_id="verifier_execution",
                    status="failed",
                    summary="Verifier could not complete.",
                    details={"error_type": type(exc).__name__},
                )],
            )

        # A verifier must not be able to attest to a different artifact/version.
        if (result.artifact_id != artifact.record.artifact_id
                or result.artifact_version != artifact.record.version):
            return VerificationReport(
                artifact_id=artifact.record.artifact_id,
                artifact_version=artifact.record.version,
                status="failed",
                summary="Verifier returned a report for a different artifact or version.",
                verifier=verifier_name,
                checks=[VerificationCheck(
                    check_id="verification_identity",
                    status="failed",
                    summary="Reported artifact identity did not match the requested artifact.",
                )],
            )

        result.verifier = verifier_name
        if any(check.status == "failed" for check in result.checks):
            result.status = "failed"
        elif any(check.status == "warning" for check in result.checks) and result.status == "passed":
            result.status = "needs_review"
        return result
