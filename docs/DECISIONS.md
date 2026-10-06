# Decision log

Format: one entry per decision. Status is `proposed`, `accepted` or `superseded by <id>`. Add new entries at the bottom; never delete old ones.

## ADR-001: rewrite the core in place, do not restart the project
**Status:** proposed (accept or change it in S-01).
**Context:** The code review found the real problems in the agent "brain": the loop and LLM layer (`app/llm.py`, `app/runtime/agent.py`), the event and trace model, and memory. That is roughly 1,000 of about 6,500 lines (an estimate). The Electron shell, UI, API, database, graph validation and tools work and need fixing, not replacing.
**Decision:** Option C. AI builds a new `app/core/` behind the `Runner` interface; Dev fixes and hardens the platform and builds a FakeRunner so the UI never waits. The old engine is frozen and deleted in S-04.
**Alternatives:** (A) restart in a new repo: about 4 to 6 focused weeks just to get back to today's features. (B) fix everything in place: lowest effort, but patches a loop built on string tags and leaves AI working in code they do not want to own.
**Consequences:** Contracts first (S-02). Temporary duplication of the engine. The 45 video tools are parked behind a switch.
**Revisit when:** the product changes shape (cloud, multi-user, mobile, a TypeScript-only runtime), you adopt a framework that dictates the structure, or either of you will not maintain this codebase. Then use PLAN.md Appendix A.

## ADR-002: build the full memory architecture in one effort
**Status:** accepted 2026-10-06. **Details:** `docs/MEMORY.md`.
**Context:** The old memory logic (`memory.py`, learned experience) has a blind spot and no safety rules. The goal is memory that is useful, visible, editable and safe.
**Decision:** Ship all layers together, each behind its own switch: semantic memory with FTS5 and Ollama embeddings, conversation compaction, episodic recall (`<recent_runs>`, `recall_run`), standing intents (reminders), and dreams (suggestions that need the user's Accept). Intents, dreams and embeddings are off by default.
**Accepted answers:**
- Q9 (M1): memory extraction runs **inline** at the end of a run; `extraction_mode: inline | background` is a setting.
- Q10 (M2): limits as proposed (500 memories per agent, 800 recall tokens, 20 active reminders, 3 auto-runs a day, $0.10 per auto-run); all are settings.
- Q11 (M3): embeddings **off by default**; with Ollama detected, settings offers a one-click enable.
- Q12 (M4): `auto_run` reminders **ship, off by default**; only the user can enable them.
**Alternatives:** keep the old memory (unsafe, blind spot); build only semantic memory now and defer the rest (rejected by the team).
**Consequences:** M2 splits into M2 and M2b; the memory contracts are frozen in S-02; about 8.5 extra AI days and 5.5 extra Dev days.

## ADR-003: large inputs are handled by handles and small pieces
**Status:** accepted 2026-10-06. **Details:** `docs/PLAN.md` section 6c.
**Context:** Large files, codebases, images and videos cannot go into a prompt, and local models have small context windows.
**Decision:** Never put a whole large input in the prompt. Tools return small pieces (ranges, search hits, summaries, downscaled images) and the agent keeps handles (workspace paths). Tool results over a size limit are saved to `.results/` in the workspace and replaced by a head plus a pointer; old results can be stubbed out mid-run.
**Alternatives:** truncate and discard (loses data); rely on a very large context window (not available on a local model).
**Consequences:** Reasoning, pagination, attachment and alias shapes join contracts v1; image parts and `response_format` are documented in C-7 (AI-owned). A-02, A-03, A-04, A-08, D-08 and D-09 grow; new cards A-15a to A-15c.

## D-1 (reserved): agent loop, hand-rolled or library
**Status:** proposed, to be written in A-01 (1-day time box).
**Default if undecided:** a hand-rolled loop of about 250 lines. The `Runner` interface does not change either way.

## D-2 (reserved): LLM backend, LiteLLM or thin adapters
**Status:** proposed, to be written in A-01.
**Requirement:** must cover Ollama chat, tool calls, `num_ctx`, structured output (`response_format`), image input and Ollama embeddings. Default if undecided: LiteLLM, pinned to a version.

<!-- Template for new entries:
## D-n (YYYY-MM-DD): <title>
Status: proposed | accepted | superseded by D-n
Context: why this came up
Decision: what we chose
Alternatives: what we rejected and why
Consequences / revisit when: ...
-->
