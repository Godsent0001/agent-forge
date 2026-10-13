# AgentForge Artifact Runtime Foundation

## Scope

The universal core manages artifact identity, immutable versions, metadata, dependencies, content integrity, and verification dispatch. It does not interpret every artifact format itself.

An artifact can be a document, image, video project, source repository, dataset, audio session, 3D scene, or another domain-specific object. The payload is opaque to the universal store. A domain adapter is responsible for understanding its format and for providing appropriate verification.

## Current implementation

- `app/contracts/artifacts.py`: typed records, version records, payloads, updates, change records, and the `ArtifactStore` protocol.
- `app/core/artifact_store.py`: SQLite registry with immutable SHA-256-addressed content blobs.
- `app/contracts/verification.py`: normalized verification report/check contracts.
- `app/core/verification.py`: type-based verifier registry and fail-closed result normalization.
- `tests/core/test_artifact_store.py` and `tests/core/test_verification.py`: core persistence and verification tests.

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

- The store is a local SQLite/filesystem implementation, not a distributed object store.
- It stores opaque bytes. Video timeline editing, image layers, repository diffs, document structure, and cybersecurity evidence need specialized adapters.
- This first version does not implement artifact deletion, retention policies, cross-project dependencies, or HTTP endpoints.
- A local filesystem and SQLite database are not a substitute for backup/replication in a multi-host deployment.
- The store's actor field is audit metadata, not authentication. The application adapter must authorize callers before invoking writes.
- Verification reports are not yet persisted. The platform adapter must decide how to attach them to an execution and its events.

## Integration boundary

Do not switch the current execution API from `ExecutionEngine` to `RunnerCore` in this workstream. The team is integrating those paths separately. When integration is ready, an adapter should:

1. Load the persisted project/agent graph and map it into `AgentGraph`.
2. Create or recover a stable execution workspace.
3. Inject the artifact store, workspace, tool factory, memory/lesson/intent stores, approval gate, cancellation token, and event emitter.
4. Translate core events/results into the application's persisted execution/event contract.
5. Preserve API request/response and frontend streaming behavior.
6. Add integration tests before changing the production route.

## Next steps

1. Run the complete Python suite and resolve any regressions.
2. Review storage quotas, metadata limits, project authorization, and multi-process concurrency.
3. Add tests for restart/reopen behavior and concurrent version updates.
4. Define the application-owned policy for verifier results and persisted audit events.
5. Add modality-specific adapters only when their concrete tools and validation rules are available.
