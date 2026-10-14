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

The developer application layer and this runtime foundation are connected through the v2 execution path:

- `POST /v2/executions` loads the persisted project/agent graph into `AgentGraph`, preserves configured tool bindings, and starts the selected runner.
- `AGENTFORGE_RUNNER=v2` selects `RunnerCore`; the default remains `fake` so a fresh development install does not unexpectedly make paid provider calls. Real-provider execution still requires valid provider configuration.
- `RunnerCore` persists final answers, tool results, and tool-declared output files into the project-scoped, versioned artifact store. Artifact persistence and verification outcomes are recorded in the existing sequenced execution event stream.
- `GET /v2/executions/{execution_id}/artifacts` lists that execution's artifacts from the persistent project store, and `GET /v2/executions/{execution_id}/artifacts/{artifact_id}?version=N` downloads a specific version. The UI displays registered artifacts alongside legacy workspace-file links.
- Each model-issued tool batch is recorded in the durable task-plan store before execution. On application startup, in-flight tasks for interrupted runs are reconciled as uncertain and are not automatically replayed.

The legacy `/executions` endpoint intentionally remains on `ExecutionEngine` for compatibility; this integration does not silently change its semantics. Remaining release work includes validating real-provider execution with configured credentials, verifying recovery under an actual process interruption, and confirming packaged Windows/Electron behavior. Do not mark this integration ready until the latest CI and end-to-end checks pass.
