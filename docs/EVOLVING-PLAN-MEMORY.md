# Evolving hierarchical plan memory

AgentForge keeps long-running work coherent across chats using three connected layers:

1. **Current plan state** — a bounded, recursively nested hierarchy stored in the existing `TaskState.state_json`. Nodes represent goals, phases, subgoals, tasks, and milestones. Nodes have stable IDs, parent IDs, source, status, and version metadata. Separate dependency edges record prerequisites without confusing them with hierarchy. A compact root-objective summary preserves the original plan’s major requirements in each compiled context; the full original objective remains in the durable task record and STATE.md projection.
2. **Durable history** — every reconciled plan delta is appended to `task_state_events` as `plan_memory_updated`, including the exact additions/status changes and the model identifier. The current plan is a projection of this history, not a replacement for it. A deterministic replay function can rebuild the hierarchy from those events. Verified task-state updates can complete matching nodes and record the execution ID that supplied the evidence.
3. **Working context** — RunnerCore compiles the root objective, current hierarchy, accepted decisions, explicit constraints, and proposals into a bounded context block. It does not replay hundreds of conversations into every prompt.

## Cross-conversation continuity

A task is a project workstream, not just a chat session. The task registry is project-wide. A user can continue a workstream in another conversation with:

```text
Resume task: <8-character-task-id>
```

The task is rebound to the new conversation while preserving its original objective, hierarchy, decisions, and event history. Resume events retain the previous and new conversation IDs for provenance. A new conversation does not silently attach itself to an unrelated active task.

## Cheap model configuration

Open **Settings → Memory → Evolving hierarchical plan memory** to enable the interpreter and choose a provider and model ID. The default suggestion is `gemini/gemini-2.5-flash-lite`, but the feature is disabled until explicitly enabled. Any supported AgentForge provider and a custom LiteLLM model ID can be selected. Provider credentials are configured separately under **Provider keys**; Ollama can be used locally.

The interpreter is deliberately small and bounded:
- It runs only for meaningful user messages, not greetings or trivial acknowledgements. Live instructions received during a running task are also reconciled before the agent resumes.
- It receives the immutable root objective, a compact projection of the current plan, and recent conversation context.
- It uses a short timeout, a small output budget, and no retry loop.
- Its LLM call is included in the run's usage totals.
- If it fails or is disabled, the main execution continues normally.

## Authority and reconciliation rules

The cheap model proposes structured deltas; it never writes directly to SQLite.

- The root objective is immutable.
- A user-authored goal or constraint is accepted only when the supplied evidence is an exact substring of the current user message.
- A user decision is marked accepted only with exact user-message evidence. Other decisions remain proposals and are explicitly labelled non-binding.
- Agent-generated phases/tasks are stored as agent-owned execution-plan nodes, separate from user goals.
- A plan node can be paused, blocked, reactivated, or superseded only when the model supplies exact user-message evidence.
- The interpreter cannot mark work complete. The execution-bound task-state update tool may complete a matching hierarchy node only when it records a verified milestone; it stores the execution ID on that node and in the append-only event payload.
- When a user explicitly changes a decision, the interpreter can identify the prior decision it supersedes; the event log preserves both the old decision and the replacement.
- Errors are treated as evidence/blockers, not new objectives.

This is an initial, evidence-gated implementation. It does not yet provide a visual plan editor, a user approval queue for every agent proposal, or automatic semantic conflict resolution across unrelated workstreams. Those require explicit UI and reconciliation work rather than trusting a low-cost model to guess.
