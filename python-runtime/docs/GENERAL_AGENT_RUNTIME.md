# General-Purpose Agent Runtime Capabilities

## Design goal

Every agent uses the same general execution foundation. Domain-specific behavior is supplied by explicit tool bindings, skills, and adapters—not by hard-coding the runtime around one content type. The shared core supports research, software work, text projects, image/video production, data workflows, and future domains as adapters become available.

## Shared layers in this branch

| Layer | Implementation | Responsibility |
|---|---|---|
| Planning and execution | `app/core/runner.py`, scheduler and budget modules | Tool loop, child-agent delegation, parallelism controls, budgets, cancellation, checkpoints |
| Durable task state | `app/core/durable_scheduler.py` | Atomic claims/transitions, persisted plans, explicit interrupted-task recovery |
| Artifacts | `app/core/artifact_store.py`, artifact contracts | Immutable versions, SHA-256 content storage, dependencies, optimistic concurrency |
| Knowledge ingestion and retrieval | `app/core/knowledge.py` | Text extraction, chunking with offsets, persistent SQLite index, lexical ranking, optional semantic reranking |
| Safe editing | `app/core/safe_editing.py` | Workspace path guards, expected-hash checks, exact replacements, preview diffs, atomic writes, backups, rollback |
| Tool exposure | `app/core/tools/workspace_capabilities.py` | Explicit `knowledge_ingest`, `knowledge_search`, and `workspace_edit` bindings while delegating other tools unchanged |
| Long-form production | `app/core/longform.py` | Outline-driven section generation, per-section checkpoints, compact continuity context, optional verification, resumable assembly |
| Domain capability adapters | `app/core/capabilities.py` | Registry, prerequisite checks, permission policy, timeout, structured outcomes for domain tools |
| Verification | `app/core/verification.py` | Type-specific verifier registry; missing verification is never reported as success |
| Memory/lessons/skills/self-model | Existing `app/core/memory`, lessons, skills, context and prompt modules | Persistent user/project knowledge and run-scoped constraints, reusable procedures, feedback from outcomes |

## Built-in workspace tool bindings

These kinds can be assigned to an agent through the existing core graph:

- `knowledge_ingest`: index a workspace-relative text, Markdown, code, HTML, JSON, or CSV file. PDF and DOCX extraction use optional packages if installed.
- `knowledge_search`: retrieve ranked snippets and original character offsets from the persistent workspace index.
- `workspace_edit`: perform targeted UTF-8 replacements only when the caller supplies the current SHA-256 and each target has the expected occurrence count. The tool creates a backup and records edit history.

The tools do not become available merely because they exist in the repository: an agent must have the corresponding tool binding. The `WorkspaceCapabilityToolFactory` wraps an existing core tool factory and delegates all non-built-in kinds to it.

## Long-form workflow

`LongFormWorkflow` accepts an ordered outline and a caller-supplied asynchronous generation adapter. It stores completed sections separately, reuses checkpoints after interruption, passes compact prior-section summaries rather than every previous page, can invoke a section verifier, and assembles a deterministic final result. This makes 200–300-page production feasible as a staged workflow, subject to the selected model's limits, generation quality, latency, and cost. It does not claim that one model call can produce 300 pages reliably.

## Domain neutrality and honest boundaries

The shared artifact and capability contracts can represent any modality. Actual editing of video timelines, image layers, audio tracks, 3D scenes, repositories, or security evidence still requires the relevant domain tool/adapter and a real verifier. The registry never treats a declared capability as proof that its external executable, credentials, or service is available.

## Application integration status

This branch extends the Python core. The existing FastAPI `/executions` endpoint still uses the legacy `ExecutionEngine`; this branch does not silently switch production traffic or change the current frontend/database contract. Therefore these core capabilities are testable and usable by a platform adapter, but they are **not yet exposed end-to-end through the current UI/API**. The remaining production integration needs an explicit DB-to-`AgentGraph` adapter, adapters for configured legacy tools and persistent stores, event/result translation, and API-level integration tests before routing live executions through `RunnerCore`.

## Validation

The Python runtime CI workflow runs the full `tests` suite on Python 3.11 and 3.12. New capability tests cover knowledge indexing/replacement, semantic-only retrieval through an injected scorer, stale-edit conflicts and rollback, resumable long-form generation, permission denial, and workspace tool bindings. CI results must be checked for the latest commit before marking this work ready.
