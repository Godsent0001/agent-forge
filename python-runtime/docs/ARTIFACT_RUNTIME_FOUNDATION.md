# AgentForge Artifact Runtime Foundation

## Scope

The universal core manages artifact identity, immutable versions, metadata, dependencies, content integrity, and verification dispatch. It does not interpret every artifact format itself.

An artifact can be a document, image, video project, source repository, dataset, audio session, 3D scene, or another domain-specific object. The payload is opaque to the universal store. A domain adapter is responsible for understanding its format and for providing appropriate verification.

## Current implementation

- `app/contracts/artifacts.py`: typed records, version records, payloads, updates, change records, and the `ArtifactStore` protocol.
- `app/core/artifact_store.py`: SQLite registry with immutable SHA-256-addressed content blobs.
- `app/contracts/verification.py`: normalized verification report/check contracts.
- `app/core/verification.py`: type-based verifier registry and fail-closed result normalization.
- `app/core/durable_scheduler.py`: SQLite-backed task-plan persistence, atomic task claims, retry state, cancellation of pending tasks, and explicit interrupted-task reconciliation.
- `app/core/execution_artifacts.py`: workspace-safe artifact persistence and verification dispatch for execution outputs.
- `app/core/runner.py`: persists tool-result artifacts and final output, emits artifact/verification events, and records task-plan claims/transitions durably with result artifact references.
- `tests/core/test_execution_artifact_lifecycle.py`: execution-lifecycle integration coverage.

The store is framework-independent and does not modify the existing SQLAlchemy application models or execution API. Its root is supplied by the caller. Registry data and blobs live below `.agentforge/artifacts/` inside that root.

## Persistence invariants

1. Artifact content versions are append-only; an update creates a new version.
2. Each blob is addressed by SHA-256 and integrity is checked on read.
3. Updates require an expected version and fail on stale writes.
4. Dependencies must exist in the same project, cannot contain duplicates, and cannot introduce cycles.
5. The registry records the change summary and actor for each version.
6. A missing verifier yields `skipped`, never `passed`.
7. Verifier exceptions and identity mismatches yield failed verification.
8. A verifier reports findings; it must not mutate artifact content. Changes go through the artifact store.

## Deliberate limitations

- The artifact and task-plan stores are local SQLite/filesystem implementations, not distributed services. RunnerCore executes the tasks and records state transitions; the durable scheduler itself remains a persistence/state-machine primitive.
- It stores opaque bytes. Video timeline editing, image layers, repository diffs, document structure, and cybersecurity evidence need specialized adapters.
- This first version does not implement artifact deletion, retention policies, or cross-project dependencies. The v2 application adapter now exposes execution-scoped artifact listing and version downloads over the persistent project store.
- A local filesystem and SQLite database are not a substitute for backup/replication in a multi-host deployment.
- The store's actor field is audit metadata, not authentication. The application adapter must authorize callers before invoking writes.
- Verification reports are emitted as RunnerCore events. They are not yet stored as standalone versioned artifacts, and no modality-specific verifier is registered by default; unverified artifacts report `skipped`.

## Integration boundary

The v2 execution path is now wired to `RunnerCore` through the developer's `ExecutionManager`, graph loader, legacy-tool adapter, workspace, approval gate, and persisted event emitter. The legacy `/executions` path remains on `ExecutionEngine` to preserve compatibility. Artifact listing/download endpoints and UI artifact cards are part of the v2 integration.

## Next steps

1. Keep the integration PR in draft until the latest Python 3.11/3.12, backend lint, frontend, and packaging checks pass.
2. Validate real-provider execution using configured credentials; the default runner mode is deliberately `fake`.
3. Add a process-interruption integration test that proves in-flight tool tasks are reconciled without automatically replaying uncertain side effects.
4. Review storage quotas, metadata limits, project authorization, and multi-process SQLite concurrency.
5. Define product policy for which artifact types require verification before they may be consumed by downstream tasks.
6. Add modality-specific adapters only when their concrete tools and validation rules are available.
