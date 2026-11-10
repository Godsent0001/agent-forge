# AgentForge hierarchical task memory

## Design goals

- Preserve the original objective and important follow-up instructions across long chats and application restarts.
- Keep ordinary memory operations deterministic and free of additional LLM calls.
- Keep the existing shared `RunnerCore` as the only execution engine.
- Keep task memory independent from semantic document indexing and optional embeddings.
- Make memory inspectable on disk without making Markdown the source of truth.

## Storage

SQLite is authoritative:

- `task_states` stores one durable task record per conversation workstream, including the immutable original objective, latest instruction, status, structured state, and version.
- `task_state_events` is an append-only record of task creation, user instructions, execution-to-task bindings, agent-authored state changes, and execution outcomes.
- Existing conversation messages and execution events remain the canonical full transcript and detailed execution trace.

The persistent project workspace also receives readable projections:

```text
.agentforge/
└── memory/
    ├── registry.json
    └── tasks/
        └── <task-id>/
            └── STATE.md
```

The projections are written atomically. If a projection write fails, SQLite remains authoritative and execution continues.

## Per-turn flow

1. The v2 execution API validates the conversation and agent.
2. Before starting the run, it creates or updates the active task state in a short SQLite transaction.
3. A normal follow-up updates `current_instruction`; it never overwrites `original_objective`.
4. A clearly explicit task-switch phrase pauses the previous task and creates a new task record.
5. A user can resume a paused task with `Resume task: <8-character-task-id>`; AgentForge reactivates that task and pauses the currently active one without discarding either state.
6. The API places a compact task header and task ID on `RunRequest`.
7. The shared RunnerCore injects the header into the root agent's system context as explicitly untrusted context. Subagents do not receive unrelated root task state.
8. Live instructions delivered to a running execution are appended to the task bound to that execution, even if another task has since become active; failed delivery is not recorded.
9. When the execution ends, AgentForge records the verified run status and a bounded output excerpt without another LLM call.

The header includes the objective, latest instruction, up to three earlier user instructions, structured constraints/decisions/progress, and recent execution outcomes. It is bounded to approximately 1,600 characters. Full history remains available in the database and in the task's Markdown projection.

## Cost and latency policy

- Persisting incoming user instructions: zero additional LLM calls.
- Recording execution outcomes: zero additional LLM calls.
- Writing Markdown projections: zero additional LLM calls.
- Agent-authored state changes use one compact tool in the existing RunnerCore tool loop, only at meaningful checkpoints; there is no separate memory agent or background summarization completion.
- Basic semantic-memory recall no longer generates query embeddings or backfills missing embeddings on the response-critical path.
- Embeddings remain optional; task continuity does not depend on an embedding provider.
- Existing recent chat history remains bounded independently from task state.

## Deliberate limitations of this first implementation

This is the durable continuity foundation, not the final memory feature set. Task identification uses conservative explicit switch phrases so ordinary follow-ups cannot accidentally erase the active objective. The root agent can batch structured decisions, constraints, verified completed steps, remaining work, blockers, and next actions through a compact task-memory tool at meaningful checkpoints. The tool writes directly to SQLite and refreshes the Markdown projection; it does not launch a separate summarization model. When invoked, it uses the normal tool-call cycle, so the agent should batch updates and avoid calling it after trivial operations. Background consolidation, FTS5 retrieval, task resume UI, and richer evidence-backed progress extraction should be added in separate tested increments.
