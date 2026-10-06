# AgentForge Testing & Handoff Guide

## Purpose

This document is the persistent testing and handoff guide for AgentForge.

It exists so that development can continue safely if the work moves to a new chat or another developer takes over. The goal is not only to prove that code compiles, but to prove that the application **works, looks usable, and remains safe to merge**.

This document should be updated when the testing workflow, project contracts, CI, or acceptance criteria change.

---

## 1. Current working rules

### Branching

- Kenny's UI/development work is done on `dev/kenny-ui`.
- `main` must not be changed directly for this work.
- Work is developed and tested on the feature branch first.
- When a change is ready, open a PR into `main`.
- The repository owner/friend reviews and approves the PR before merge.
- Do not bypass that approval step.

### Development gate

Use this loop for every meaningful change:

> **Change → test → inspect → fix → retest → next change**

For UI work specifically:

> **Change → typecheck/build → run the app → visually inspect → interact with it → fix → retest**

Do not stack several untested UI changes and only test at the end.

---

## 2. What "tested" means

A change is not considered complete merely because the code exists or TypeScript compiles.

Testing has five layers:

1. **Static/code checks**
2. **Automated functional tests**
3. **Visual and usability testing**
4. **End-to-end workflow testing**
5. **Final acceptance/PR verification**

A defect found at any layer blocks the change from being considered finished until it is fixed and retested.

---

## 3. Layer 1 — Static and build checks

The project must at minimum be checked for:

### Frontend

- TypeScript compilation/typecheck.
- Production Vite build.
- Frontend test suite once the Vitest infrastructure is present.

The project currently exposes:

```bash
npm run build
```

The current `package.json` does **not yet expose** the planned `test` or `typecheck` scripts, so those should not be claimed as passing until the corresponding tooling/scripts actually exist.

### Python runtime

The project plan specifies the Python test suite should be run with:

```bash
cd python-runtime
uv run pytest -m "not live"
```

Live LLM tests must not be part of normal CI because they can spend money. They are intended for deliberate/manual runs with a cheap model and hard budgets.

### Important rule

Never report a test as passing unless it was actually executed and the result is known.

If the available tooling cannot execute the test suite, report that limitation instead of guessing.

---

## 4. Layer 2 — Automated functional tests

Automated tests should cover the behaviour that can be checked deterministically.

### Backend / runtime

The project testing plan calls for coverage around:

- Graph validation:
  - self-link rejected
  - cycle rejected
  - valid chain accepted
  - depth greater than 8 rejected
- Memory behaviour:
  - compaction/context behaviour
  - known blind-spot case tracked explicitly
- Execution lifecycle:
  - POST execution returns quickly instead of waiting for the whole run
  - WebSocket events arrive in sequence
  - reconnect with `after_seq` receives only newer events
  - cancellation ends the run as cancelled
  - startup cleanup is tested
- FakeRunner/FakeLLM scenarios:
  - single answer
  - tool call
  - parallel work
  - unknown tool
  - bad arguments
  - sub-agent execution
  - loops
  - budget limits
  - cancellation
  - maximum depth
  - cycle protection

### Contract testing

The event contract in `CONTRACTS.md` is a testing source of truth.

Important invariants include:

- `execution_started` is first.
- `execution_ended` is last.
- `seq` starts at 1.
- `seq` increases exactly by 1 for each execution event.
- Root agent span has no parent.
- Child spans identify their parent with `parent_span_id`.
- Event payloads are bounded/truncated according to the contract.
- Tool calls and delegated sub-agent spans preserve the expected hierarchy.

Contract changes require coordinated changes to the documentation, Python models, and TypeScript types, with the required review process.

---

## 5. Layer 3 — Visual and usability testing

Automated tests cannot prove that the application looks good.

Every significant UI change should therefore be manually inspected in the running application.

### Layout

Check:

- No unintended wrapping or second-row panels.
- Main columns stay in their intended positions.
- Panels do not overlap.
- Content stays inside the viewport.
- Horizontal and vertical scrolling behave intentionally.
- Resizing the window does not destroy the layout.
- Narrower window sizes remain usable.

### Typography and spacing

Check:

- Headings have a clear hierarchy.
- Text is readable.
- Buttons and controls have consistent sizing.
- Padding and gaps are consistent.
- Empty space is intentional rather than caused by layout bugs.
- Long text does not unexpectedly overflow.

### Interaction

Check:

- Buttons visibly respond to clicks.
- Tabs actually switch views.
- Agent selection works.
- Chat input behaves correctly.
- Configuration controls behave correctly.
- Run controls provide visible state changes.
- Execution information updates when a run starts.
- Stop/cancel controls behave correctly where implemented.

### State handling

Manually inspect:

- Loading state.
- Empty state.
- Normal/ready state.
- Error state.
- Long-running execution state.
- Completed execution state.
- Failed execution state.
- Cancelled execution state.

A UI that only looks correct in the happy path is not finished.

---

## 6. Layer 4 — End-to-end testing

The core user journey should be tested as a complete workflow.

### Primary smoke flow

1. Start AgentForge.
2. Confirm the Python runtime/sidecar becomes available.
3. Confirm the workspace loads.
4. Create/select a project.
5. Create/select an agent.
6. Configure the agent.
7. Open Chat.
8. Send a task.
9. Start execution.
10. Confirm the execution appears in the UI.
11. Watch the execution trace/tree update.
12. Confirm tool calls appear as tool activity rather than ordinary user messages.
13. Confirm the final response appears.
14. Inspect the execution result.
15. Run another task.
16. Confirm previous state does not corrupt the new run.

### Failure-path flow

Also test:

- Runtime unavailable.
- Invalid tool.
- Bad tool arguments.
- Tool failure.
- LLM failure.
- Cancellation/Stop.
- Sub-agent execution.
- Recursive/depth-limit protection.
- Budget exhaustion.
- Reconnecting to an execution stream.

Failure handling is part of the product, not an optional extra.

---

## 7. Current UI change being verified

The current `dev/kenny-ui` branch contains the layout correction in `src/App.tsx`.

### Problem that was fixed

The previous three-column grid had four sibling children:

- AgentTree
- Chat
- Config
- ExecutionTree

That meant the fourth child could be placed on an unintended grid row.

### Current structure

The center area now contains Chat/Config inside a single wrapper:

```text
┌──────────────┬──────────────────────────────┬────────────────┐
│ Agent Tree   │ Chat / Config                │ Execution Tree  │
│              │                              │                │
│              │                              │                │
└──────────────┴──────────────────────────────┴────────────────┘
```

The relevant layout is:

```tsx
<div className="flex-1 grid grid-cols-[280px_1fr_320px] min-h-0 overflow-hidden">
  <AgentTree />

  <div className="min-w-0 h-full overflow-hidden">
    {activeTab === "chat" ? (
      <div className="h-full flex flex-col">
        <AgentChat onRunExecution={setActiveExecutionId} />
      </div>
    ) : (
      <div className="h-full flex flex-col">
        <AgentEditor />
      </div>
    )}
  </div>

  <ExecutionTree executionId={activeExecutionId} />
</div>
```

This change was committed to `dev/kenny-ui`.

Before adding more UI changes, verify this layout in the running application.

---

## 8. Testing the current layout change

The immediate verification sequence is:

### Automated

- Run the available frontend build/type checks.
- Run the Python test suite if the runtime/tooling is available.
- Check CI status if a CI workflow exists.
- Do not invent a passing result when a test cannot be executed.

### Manual

Open the application and check:

- [ ] Agent Tree remains in the left column.
- [ ] Chat remains in the centre column.
- [ ] Execution Tree remains in the right column.
- [ ] Switching Chat → Config keeps the centre column.
- [ ] Execution Tree does not fall below the main content.
- [ ] Long chat content scrolls inside its intended area.
- [ ] Long execution content scrolls inside its intended area.
- [ ] Window resizing does not create unexpected overflow.
- [ ] Run actions still update the selected execution.
- [ ] No console/runtime errors appear during the smoke flow.

Only after this passes should another UI change be stacked on top.

---

## 9. CI requirements

The project planning documentation defines the desired CI baseline.

The intended CI should include:

### Python job

```bash
cd python-runtime
uv run pytest -m "not live"
```

### Frontend job

```bash
npm ci
npm test -- --run
npm run build
```

The frontend test infrastructure is expected to use:

- Vitest
- jsdom
- Testing Library for React
- jest-dom

The frontend configuration should use a jsdom test environment.

A smoke test should exist once the D-02 testing baseline is implemented.

### CI rule

A green build is necessary, but not sufficient.

CI proves automated checks pass. It does not replace visual inspection or end-to-end manual testing.

---

## 10. Definition of done

A feature/change is ready for PR review only when:

- [ ] Intended behaviour is implemented.
- [ ] Relevant automated tests exist or the absence is explicitly documented.
- [ ] Type/build checks pass when available.
- [ ] Relevant Python tests pass when applicable.
- [ ] UI has been manually inspected when UI changed.
- [ ] Main user flow still works.
- [ ] Important failure paths were considered/tested.
- [ ] No obvious console/runtime errors remain.
- [ ] Documentation is updated if behaviour, configuration, or contracts changed.
- [ ] No new silent `except Exception: pass` handling was introduced.
- [ ] No new hard-coded ports/paths were introduced where project guidance prohibits them.
- [ ] The change is on the correct feature branch.
- [ ] PR is ready for review.
- [ ] Repository owner/friend reviews and approves before merge.

---

## 11. M3 / personal acceptance gate

The project plan defines a broader installed-build acceptance gate.

When the project reaches that stage, verify:

1. Installer builds on the target OS.
2. Installer works on a clean user account/VM.
3. Application data is stored in the OS user-data location.
4. Data survives reinstall.
5. Quitting the app leaves no Python process behind.
6. Starting the application twice focuses the first window instead of launching a duplicate.
7. There are no unexpected external network requests at startup.
8. System check is green or provides clear actionable fixes.
9. Per-run/project cost is visible.
10. Three starter templates run successfully.
11. A five-run soak test completes without a crash.

P0 defects must be fixed before the personal-use release gate is considered complete.

---

## 12. How to continue this project from a new chat

If this project is opened in another chat, the first things to inspect are:

1. `PLAN.md`
2. `CONTRACTS.md`
3. `TASKS-DEV.md`
4. `TASKS-AI-1.md`
5. This file: `TESTING.md`
6. Current branch and recent commits.
7. Current CI/test status.
8. The files changed by the most recent unfinished task.

Then determine:

- What branch is active.
- What the last completed change was.
- What was actually tested.
- What remains unverified.
- Whether `main` has changed independently.
- Whether a PR is waiting for review.
- Whether the current task is blocked by missing test infrastructure.

Never assume a task is complete merely because a previous conversation said it was complete. Re-check the repository state.

---

## 13. Documentation sources

This guide is derived from the AgentForge project planning/contract documents:

- `PLAN.md` — overall project plan, definition of done, acceptance gates, testing strategy.
- `CONTRACTS.md` — API/event contracts and contract-testing requirements.
- `TASKS-DEV.md` — developer task cards and D-02/D-04/D-06/D-07 testing requirements.
- `TASKS-AI-1.md` — AI-side task responsibilities and FakeLLM/runtime testing expectations.
- `Agentforge.txt` — architecture, known problems, implementation risks, and proposed test scenarios.

When these documents change, this testing guide should be reconciled with them.

For external tooling, use the current official documentation for the installed versions of TypeScript, Vite, Electron, Vitest, React Testing Library, Python/pytest, uv, and GitHub Actions rather than relying on outdated examples.

---

## 14. Handoff status

**Current working branch:** `dev/kenny-ui`

**Current focus:** establish a reliable test/inspection gate before continuing feature work.

**Last known UI change:** App layout correction in `src/App.tsx`.

**Immediate next action:** test the current layout change before stacking another UI change.

**Merge policy:** feature branch → automated/manual verification → PR → repository owner/friend approval → merge to `main`.

**Core rule:**

> If it has not been tested, it is not finished.
