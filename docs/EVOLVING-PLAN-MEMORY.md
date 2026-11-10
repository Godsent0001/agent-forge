# Evolving hierarchical plan memory

AgentForge keeps long-running work coherent across chats using three connected layers:

1. **Current plan state** — a bounded, recursively nested hierarchy stored in the existing `TaskState.state_json`. Nodes represent goals, phases, subgoals, tasks, and milestones. Nodes have stable IDs, parent IDs, source, status, and version metadata. Separate dependency edges record prerequisites without confusing them with hierarchy. A compact root-objective summary preserves the original plan’s major requirements in each compiled context; the full original objective remains in the durable task record and STATE.md projection.
2. **Durable history** — every reconciled plan delta is appended to `task_state_events` as `plan_memory_updated`, including the exact additions/status changes and the model identifier. The current plan is a projection of this history, not a replacement for it. A deterministic replay function can rebuild the hierarchy from those events. Verified task-state updates can complete matching nodes and record the execution ID that supplied the evidence.
3. **Working context** — RunnerCore compiles the root objective, current hierarchy, accepted decisions, explicit constraints, and proposals into a bounded context block. It does not replay hundreds of conversations into every prompt.

## Cross-conversation continuity

A task is a project workstream, not just a chat session. The task registry is project-wide. A user can continue a workstream in another conversation with a task ID, or simply say “Continue” when there is exactly one active/paused workstream for that project and agent. AgentForge auto-resumes only an unambiguous match; otherwise it does not guess. The explicit form is:

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
- A user-authored goal or constraint is accepted only when the supplied evidence is an exact substring of a stored user-authored message for that workstream. The main task-memory tool applies the same exact-match rule before a decision or constraint enters the binding user state.
- A user decision is marked accepted only when its text appears verbatim in exact user-message evidence. Other decisions remain proposals and are explicitly labelled non-binding.
- Agent-generated phases/tasks are stored as agent-owned execution-plan nodes, separate from user goals. The main agent can add its own execution-plan nodes and prerequisite edges through the existing execution-bound task-memory tool at meaningful checkpoints; the cheap interpreter continuously reconciles later user and execution evidence into that same hierarchy.
- A user-owned plan node can be paused, blocked, reactivated, or superseded only with exact evidence from a user-authored message. Agent-owned execution nodes can be updated using exact evidence from recent tool results or conversation history, but cannot be marked complete by the interpreter.
- The interpreter cannot mark work complete. The execution-bound task-state update tool may complete a matching hierarchy node only when it records a verified milestone; it stores the execution ID on that node and in the append-only event payload.
- When a user explicitly changes a decision, the interpreter can identify the prior decision it supersedes; the event log preserves both the old decision and the replacement.
- Errors are treated as evidence/blockers, not new objectives.

This is an initial, evidence-gated implementation. It does not yet provide a visual plan editor, a user approval queue for every agent proposal, or automatic semantic conflict resolution across unrelated workstreams. Those require explicit UI and reconciliation work rather than trusting a low-cost model to guess.


## Periodic plan-integrity auditing

When the low-cost plan-memory interpreter is enabled, AgentForge performs a semantic integrity audit during the initial meaningful plan reconciliation and then every five reconciliations. The audit shares that reconciliation's model call rather than introducing a separate call on every message. It checks:

- Whether the immutable original objective is still represented by the current plan.
- Whether accepted requirements, constraints, or decisions have disappeared from the current hierarchy.
- Whether a completed task now has a missing, incomplete, superseded, or subsequently changed prerequisite.
- Whether accepted decisions conflict with one another.
- Whether subgoals appear stale or no longer contribute to the root objective.
- Whether the active execution path still leads toward the original goal.

Findings are bounded, typed, linked to existing plan-node IDs where possible, and appended as `plan_integrity_audited` task events. The latest audit is also included in the compiled working context so the main agent can address open concerns. The audit is **read-only**: it cannot change the root objective, accept or reject decisions, alter task status, or rewrite the execution plan. It reports evidence-backed concerns for the main agent and user to resolve. If the optional interpreter is disabled or the run budget cannot afford the memory call, auditing is skipped and normal execution continues.
