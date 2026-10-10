"""Runner v2 (the agent loop engine) for AgentForge Core."""
import asyncio
import copy
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.contracts.events import EventDraft
from app.contracts.graph import AgentGraph, AgentSpec, ToolBinding
from app.contracts.memory import IntentStore, LessonStore, MemoryStore, RunHistory
from app.contracts.naming import dedupe_names, sanitize_tool_name
from app.contracts.run import RunRequest, RunResult, Totals
from app.contracts.runner import ApprovalGate, CancelToken, Clock, Emit, ToolFactory
from app.contracts.tools import ArtifactRef, Permission, RunWorkspace, ToolContext, ToolError, ToolResult
from app.core.budget import BudgetExceededError, BudgetTracker
from app.core.checkpoint import AgentFrame, ExecutionCheckpoint, SQLiteCheckpointStore
from app.core.context import ContextCompiler
from app.core.scheduler import ScheduledTask, TaskPlan
from app.core.claim_check import ClaimCheckEnvelope, ClaimCheckSummary, TaskDirective
from app.core.lessons import format_lessons_block, reflect_on_signal
from app.core.llm.adapter import complete as adapter_complete
from app.core.llm.fake import FakeLLM
from app.core.llm.pricing import get_context_window
from app.core.llm.types import LLMContextTooLong, LLMError, LLMParams, LLMTurn, ToolCall, ToolSpec, Usage
from app.core.memory.episodic import build_recent_runs_block
from app.core.memory.extractor import extract_and_store_memories
from app.core.memory.recall import recall_memories
from app.core.prompt_builder import build_system_prompt
from app.core.skills.types import SkillManifest
from app.core.skills.registry import select_skill
from app.core.spans import span
from app.core.tools.yield_time import YieldTimeTool

logger = logging.getLogger(__name__)
DEFAULT_MAX_PARALLEL_TOOL_CALLS = 4
DEFAULT_TOOL_TIMEOUT_SECONDS = 120
DEFAULT_MAX_SCHEDULED_TASKS = 100


class RunnerCore:
    """Core Runner implementation handling agent trees, tool execution, spans, and budgets."""

    def __init__(self, fake_llm: FakeLLM | None = None):
        self.fake_llm = fake_llm

    async def run(
        self,
        req: RunRequest,
        *,
        graph: AgentGraph,
        emit: Emit,
        cancel: CancelToken,
        approvals: ApprovalGate,
        workspace: RunWorkspace,
        tools: ToolFactory,
        memory: MemoryStore,
        lessons: LessonStore,
        intents: IntentStore,
        run_history: RunHistory,
        clock: Clock | None = None,
    ) -> RunResult:
        budget = BudgetTracker(req.options.budget, max_parallel_tools=getattr(req.options, "max_parallel_tool_calls", DEFAULT_MAX_PARALLEL_TOOL_CALLS))
        root_spec = graph.agents.get(graph.root_id)
        if not root_spec:
            return RunResult(
                status="error",
                error=f"Root agent '{graph.root_id}' not found in graph.",
                totals=budget.totals,
            )

        active_agent_ids: set[str] = set()
        agent_revision_counts: dict[str, int] = {}
        clock_fn: Clock = clock or (lambda: datetime.now(timezone.utc))

        checkpoint_store = SQLiteCheckpointStore(Path(workspace.root) / ".agentforge" / "checkpoints.sqlite3")
        graph_fingerprint = _fingerprint(graph.model_dump(mode="json"))
        request_fingerprint = _fingerprint(req.model_dump(mode="json", exclude={"execution_id"}))
        prior_checkpoint = await checkpoint_store.load(req.execution_id)
        resume_state: dict[str, Any] | None = None
        root_invocation_id = str(uuid.uuid4())
        root_span_id: str | None = None
        active_spans: dict[str, dict[str, Any]] = {}
        last_checkpoint_state: dict[str, Any] = {}
        pending_reminder_ids: list[str] = []
        checkpoint_created_at = datetime.now(timezone.utc)
        if prior_checkpoint is not None:
            if prior_checkpoint.graph_fingerprint != graph_fingerprint:
                return RunResult(status="error", error="Cannot resume execution: agent graph changed since checkpoint.", totals=budget.totals)
            if prior_checkpoint.metadata.get("request_fingerprint") != request_fingerprint:
                return RunResult(status="error", error="Cannot resume execution: request differs from checkpoint.", totals=budget.totals)
            if prior_checkpoint.frames:
                root_invocation_id = prior_checkpoint.frames[0].invocation_id
                root_span_id = prior_checkpoint.frames[0].span_id
            active_spans = {
                str(item["span_id"]): dict(item)
                for item in prior_checkpoint.metadata.get("active_spans", [])
                if isinstance(item, dict) and item.get("span_id")
            }
            checkpoint_created_at = prior_checkpoint.created_at
            if prior_checkpoint.budget_state:
                budget.restore(prior_checkpoint.budget_state)
            resume_state = copy.deepcopy(prior_checkpoint.task_state) or None
            pending_reminder_ids = list((resume_state or {}).get("pending_reminder_ids", []))
            last_checkpoint_state.update(copy.deepcopy(resume_state or {}))
            # A resumed invocation is active again; terminal status from the previous
            # interruption remains available in the result but must not label new writes.
            last_checkpoint_state["checkpoint_status"] = "running"
            last_checkpoint_state.pop("terminal_error", None)
            if root_span_id and not active_spans and not (
                resume_state and isinstance(resume_state.get("final_output"), str)
            ):
                return RunResult(
                    status="error",
                    error="Checkpoint has no active root span and no final output; refusing an event-contract-unsafe resume.",
                    totals=budget.totals,
                )
            if resume_state and resume_state.get("final_output") is not None and not active_spans:
                resume_state["root_span_closed"] = True
                last_checkpoint_state.update(copy.deepcopy(resume_state))

        async def write_checkpoint() -> None:
            state = last_checkpoint_state
            messages = copy.deepcopy(state.get("messages", []))
            completed = {
                str(m.get("tool_call_id")): str(m.get("content", ""))
                for m in messages if m.get("role") == "tool" and m.get("tool_call_id")
            }
            frame = AgentFrame(
                invocation_id=root_invocation_id,
                agent_id=graph.root_id,
                span_id=root_span_id,
                task=req.task,
                depth=0,
                iteration=int(state.get("iterations", 0)),
                messages=messages,
                pending_tool_call_ids=list(state.get("pending_tool_call_ids", [])),
                completed_tool_results=completed,
            )
            checkpoint = ExecutionCheckpoint(
                execution_id=req.execution_id,
                graph_fingerprint=graph_fingerprint,
                status=str(state.get("checkpoint_status", "running")),
                created_at=checkpoint_created_at,
                updated_at=datetime.now(timezone.utc),
                frames=[frame],
                task_state=copy.deepcopy(state),
                budget_state=budget.snapshot(),
                metadata={"request_fingerprint": request_fingerprint,
                          "resume_semantics": "in-flight-tool-outcomes-are-not-replayed",
                          "root_span_id": root_span_id,
                          "active_spans": list(active_spans.values())},
            )
            await checkpoint_store.save(checkpoint)

        async def save_checkpoint(state: dict[str, Any]) -> None:
            nonlocal root_span_id
            last_checkpoint_state.clear()
            last_checkpoint_state.update(copy.deepcopy(state))
            # Include the delivery ledger even when the run completes without tools.
            last_checkpoint_state["pending_reminder_ids"] = list(pending_reminder_ids)
            if state.get("root_span_id"):
                root_span_id = str(state["root_span_id"])
            await write_checkpoint()

        async def tracked_emit(draft: EventDraft) -> None:
            nonlocal root_span_id
            if draft.type == "span_started" and draft.span_id:
                active_spans[draft.span_id] = {
                    "span_id": draft.span_id,
                    "parent_span_id": draft.parent_span_id,
                    "kind": draft.kind,
                    "name": draft.name,
                }
                if draft.kind == "agent" and draft.parent_span_id is None:
                    root_span_id = draft.span_id
            await emit(draft)
            if draft.type == "span_ended" and draft.span_id:
                active_spans.pop(draft.span_id, None)
            await write_checkpoint()

        if prior_checkpoint is not None and active_spans:
            def _span_depth(span_id: str) -> int:
                depth = 0
                parent = active_spans.get(span_id, {}).get("parent_span_id")
                seen = {span_id}
                while parent and parent in active_spans and parent not in seen:
                    seen.add(parent)
                    depth += 1
                    parent = active_spans[parent].get("parent_span_id")
                return depth

            abandoned_spans = sorted(
                (sid for sid in active_spans if sid != root_span_id),
                key=_span_depth, reverse=True,
            )
            for abandoned_id in abandoned_spans:
                abandoned = active_spans.get(abandoned_id)
                if abandoned:
                    await tracked_emit(EventDraft(
                        type="span_ended",
                        span_id=abandoned_id,
                        parent_span_id=abandoned.get("parent_span_id"),
                        kind=abandoned.get("kind"),
                        name=abandoned.get("name"),
                        status="error",
                        data={"error": "Execution interrupted; span closed during resume."},
                    ))

        try:
            final_output = ""
            if resume_state and isinstance(resume_state.get("final_output"), str):
                final_output = resume_state["final_output"]
            else:
                final_output = await self._run_agent(
                agent_id=graph.root_id,
                graph=graph,
                req=req,
                task=req.task,
                history=list(req.history),
                history_summary=req.history_summary,
                parent_span_id=None,
                depth=0,
                emit=tracked_emit,
                cancel=cancel,
                approvals=approvals,
                workspace=workspace,
                tools_factory=tools,
                memory=memory,
                lessons=lessons,
                intents=intents,
                run_history=run_history,
                budget=budget,
                active_agent_ids=active_agent_ids,
                agent_revision_counts=agent_revision_counts,
                clock=clock_fn,
                checkpoint=save_checkpoint,
                resume_state=resume_state,
                pending_reminder_ids=pending_reminder_ids,
                resume_span_id=root_span_id if prior_checkpoint is not None and root_span_id and not (resume_state or {}).get("root_span_closed") else None,
            )

            if not (resume_state and isinstance(resume_state.get("final_output"), str)):
                await save_checkpoint({
                    **last_checkpoint_state,
                    "final_output": final_output,
                    "root_span_id": root_span_id,
                    "root_span_closed": True,
                    "pending_tool_call_ids": [],
                })
            elif root_span_id and not resume_state.get("root_span_closed"):
                if root_spec.memory_enabled and memory:
                    try:
                        await self._extract_memories(
                            root_spec=root_spec, req=req, final_output=final_output,
                            memory=memory, emit=tracked_emit,
                            parent_span_id=root_span_id, budget=budget,
                        )
                    except Exception:
                        await tracked_emit(EventDraft(
                            type="span_ended", span_id=root_span_id, parent_span_id=None,
                            kind="agent", name=root_spec.name, status="error",
                            data={"error": "Memory extraction failed during resume."},
                        ))
                        raise
                await tracked_emit(EventDraft(
                    type="span_ended", span_id=root_span_id, parent_span_id=None,
                    kind="agent", name=root_spec.name, status="ok",
                    data={"output_preview": final_output[:2000]},
                ))
                await save_checkpoint({
                    **resume_state, "final_output": final_output,
                    "root_span_id": root_span_id, "root_span_closed": True,
                    "pending_tool_call_ids": [],
                })

            if root_spec.lessons_enabled and lessons:
                recovery = _find_recovered_tool_error(last_checkpoint_state.get("messages", []))
                if recovery:
                    error_message, recovered_output = recovery
                    try:
                        await reflect_on_signal(
                            agent_id=root_spec.id,
                            execution_id=req.execution_id,
                            error_message=error_message,
                            recovered_output=recovered_output or final_output,
                            store=lessons,
                        )
                    except Exception:
                        logger.debug("Recovery lesson reflection failed", exc_info=True)

            if pending_reminder_ids:
                await intents.mark_fired(pending_reminder_ids, _clock_now(clock_fn))
            await checkpoint_store.delete(req.execution_id)
            return RunResult(
                status="completed",
                final_output=final_output,
                totals=budget.totals,
            )

        except BudgetExceededError as exc:
            last_checkpoint_state.update({
                "checkpoint_status": "budget_exceeded",
                "pending_reminder_ids": list(pending_reminder_ids),
                "terminal_error": str(exc),
            })
            await write_checkpoint()
            return RunResult(
                status="budget_exceeded",
                error=str(exc),
                totals=budget.totals,
            )
        except asyncio.CancelledError:
            last_checkpoint_state.update({
                "checkpoint_status": "cancelled",
                "pending_reminder_ids": list(pending_reminder_ids),
                "terminal_error": "Run was cancelled by user.",
            })
            await write_checkpoint()
            return RunResult(
                status="cancelled",
                error="Run was cancelled by user.",
                totals=budget.totals,
            )
        except Exception as exc:
            last_checkpoint_state.update({
                "checkpoint_status": "error",
                "pending_reminder_ids": list(pending_reminder_ids),
                "terminal_error": str(exc),
            })
            await write_checkpoint()
            logger.exception("Run execution error")
            return RunResult(
                status="error",
                error=str(exc),
                totals=budget.totals,
            )

    async def _run_agent(
        self,
        agent_id: str,
        graph: AgentGraph,
        req: RunRequest,
        task: str,
        history: list[Any],
        history_summary: str,
        parent_span_id: str | None,
        depth: int,
        emit: Emit,
        cancel: CancelToken,
        approvals: ApprovalGate,
        workspace: RunWorkspace,
        tools_factory: ToolFactory,
        memory: MemoryStore,
        lessons: LessonStore,
        intents: IntentStore,
        run_history: RunHistory,
        budget: BudgetTracker,
        active_agent_ids: set[str],
        agent_revision_counts: dict[str, int],
        clock: Clock,
        skill_manifest: SkillManifest | None = None,
        pending_reminder_ids: list[str] | None = None,
        checkpoint: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        resume_state: dict[str, Any] | None = None,
        resume_span_id: str | None = None,
    ) -> str:
        cancel.raise_if_cancelled()
        budget.check_limits()
        pending_reminder_ids = pending_reminder_ids if pending_reminder_ids is not None else []

        if agent_id in active_agent_ids:
            raise RuntimeError(f"Cycle detected in agent graph for agent '{agent_id}'")
        if depth > req.options.max_depth:
            raise RuntimeError(f"Maximum delegation depth reached ({depth} > {req.options.max_depth})")
        # Copy the ancestry per invocation: sibling invocations of the same agent definition
        # must not mutate or observe one another's active path.
        agent_path = set(active_agent_ids)
        agent_path.add(agent_id)
        spec = graph.agents[agent_id]
        if skill_manifest is None:
            available_tools = {name for binding in spec.tools for name in (binding.name, binding.kind)}
            try:
                skill_manifest = select_skill(workspace.root, task, available_tools)
            except (OSError, ValueError, TypeError):
                logger.debug("Skill discovery skipped for agent %s", spec.id, exc_info=True)

        try:
            async with span(
                emit,
                kind="agent",
                name=spec.name,
                parent_span_id=parent_span_id,
                data={
                    "agent_id": spec.id,
                    "depth": depth,
                    "input_preview": task[:2000],
                },
                span_id=resume_span_id if depth == 0 else None,
                emit_start=not (depth == 0 and resume_span_id is not None),
            ) as agent_span_id:

                async def persist_state(state: dict[str, Any]) -> None:
                    if depth == 0 and checkpoint:
                        payload = dict(state)
                        payload["root_span_id"] = agent_span_id
                        payload["pending_reminder_ids"] = list(pending_reminder_ids)
                        await checkpoint(payload)

                # 1. Memory recall
                memory_block = ""
                if spec.memory_enabled and memory:
                    try:
                        _, memory_block = await recall_memories(
                            store=memory,
                            agent_id=spec.id,
                            query=task,
                            recall_budget_tokens=req.options.memory.recall_budget_tokens,
                            embedding_model=req.options.memory.embedding_model,
                        )
                    except Exception as e:
                        logger.warning(f"Memory recall error: {e}")
                memory_block = ContextCompiler.bound_block(memory_block, 3_200, "memory recall")

                # 2. Recent problem runs
                recent_runs_block = ""
                if req.options.memory.episodic and run_history and depth == 0:
                    recent_runs_block = await build_recent_runs_block(run_history, spec.id)
                recent_runs_block = ContextCompiler.bound_block(recent_runs_block, 1_200, "recent runs")

                # 3. Due reminders
                reminders_block = ""
                if req.options.memory.intents and intents and depth == 0:
                    now_utc = _clock_now(clock)
                    due_intents = await intents.due_for_run(spec.id, now_utc)
                    if due_intents:
                        # A reminder is acknowledged only after its containing run
                        # completes. If interrupted, it remains deliverable.
                        # If messages are reconstructed after interruption, render due
                        # reminders again. Existing transcript restoration takes precedence
                        # when the previous prompt was already checkpointed.
                        reminders_block = "\n".join(f"- {item.text}" for item in due_intents)
                        already_pending = set(pending_reminder_ids)
                        pending_reminder_ids.extend(
                            item.id for item in due_intents if item.id not in already_pending
                        )

                # 4. Lessons
                lessons_block = ""
                if spec.lessons_enabled and lessons:
                    lessons_block = await format_lessons_block(lessons, spec.id)
                lessons_block = ContextCompiler.bound_block(lessons_block, 1_800, "lessons")
                reminders_block = ContextCompiler.bound_block(reminders_block, 1_000, "reminders")

                # 5. Temporal Context
                now_dt = _clock_now(clock)
                temporal_context = {
                    "current_time_iso": now_dt.isoformat(),
                    "epoch_timestamp_ms": int(now_dt.timestamp() * 1000),
                    "session_elapsed_ms": int(budget.elapsed_seconds * 1000),
                    "remaining_budget_ms": int((req.options.budget.max_seconds - budget.elapsed_seconds) * 1000) if req.options.budget.max_seconds else None,
                }

                # 6. Build runtime-derived self-model. This is not memory, lessons, or a skill.
                self_model_block = _build_self_model(
                    spec=spec, graph=graph, req=req, budget=budget,
                    skill_manifest=skill_manifest, depth=depth,
                )

                # 7. Build system prompt
                system_prompt = build_system_prompt(
                    spec=spec,
                    memory_block=memory_block,
                    reminders_block=reminders_block,
                    recent_runs_block=recent_runs_block,
                    lessons_block=lessons_block,
                    history_summary_block=ContextCompiler.bound_block(history_summary, 6_000, "conversation summary"),
                    skill_manifest=skill_manifest,
                    self_model_block=self_model_block,
                    temporal_context=temporal_context,
                )

                messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
                for msg in history:
                    messages.append({"role": msg.role if hasattr(msg, "role") else msg["role"], "content": msg.content if hasattr(msg, "content") else msg["content"]})
                messages.append({"role": "user", "content": task})
                if depth == 0 and resume_state and isinstance(resume_state.get("messages"), list):
                    messages = copy.deepcopy(resume_state["messages"])

                # 7. Assemble tools
                native_tool_specs, tool_instances = self._assemble_tools(spec, graph, tools_factory, memory, intents, run_history)

                iterations = int(resume_state.get("iterations", 0)) if depth == 0 and resume_state else 0
                tool_call_history: list[str] = list(resume_state.get("tool_call_history", [])) if depth == 0 and resume_state else []
                pending_ids = list(resume_state.get("pending_tool_call_ids", [])) if depth == 0 and resume_state else []
                completed_tool_results = dict(resume_state.get("completed_tool_results", {})) if depth == 0 and resume_state else {}
                if pending_ids or completed_tool_results:
                    existing_result_ids = {
                        str(m.get("tool_call_id")) for m in messages
                        if m.get("role") == "tool" and m.get("tool_call_id")
                    }
                    # Completed calls are restored from their checkpointed results; only
                    # calls still marked pending are uncertain and must not be replayed.
                    for completed_id, completed_content in completed_tool_results.items():
                        if str(completed_id) not in existing_result_ids:
                            messages.append({"role": "tool", "tool_call_id": str(completed_id), "content": str(completed_content)})
                            existing_result_ids.add(str(completed_id))
                    for pending_id in pending_ids:
                        if str(pending_id) in existing_result_ids:
                            continue
                        messages.append({
                            "role": "tool",
                            "tool_call_id": pending_id,
                            "content": "ERROR: Execution was interrupted while this tool call was in flight. Its side-effect outcome is unknown; do not blindly repeat it. Reconcile the outcome before retrying.",
                        })
                    if checkpoint:
                        await persist_state({"messages": messages, "iterations": iterations,
                                          "tool_call_history": tool_call_history,
                                          "pending_tool_call_ids": [], "completed_tool_results": {}})

                context_window = get_context_window(spec.model)
                reserved_output_tokens = max(0, int(spec.params.max_tokens or 0))
                usable_context_tokens = max(1_400, context_window - reserved_output_tokens - 1_000)
                context_compiler = ContextCompiler(
                    max_context_chars=min(48_000, max(4_000, usable_context_tokens * 3))
                )
                while True:
                    cancel.raise_if_cancelled()
                    budget.check_limits()
                    iterations += 1
                    if depth == 0 and checkpoint:
                        await persist_state({"messages": messages, "iterations": iterations,
                                          "tool_call_history": tool_call_history,
                                          "pending_tool_call_ids": []})

                    if iterations > req.options.max_iterations:
                        final_text = await self._force_text_turn(
                            spec, messages, agent_span_id, emit, budget
                        )
                        if depth == 0 and checkpoint:
                            await persist_state({"messages": messages, "iterations": iterations,
                                                 "tool_call_history": tool_call_history,
                                                 "pending_tool_call_ids": [], "final_output": final_text})
                        if depth == 0 and spec.memory_enabled and memory:
                            await self._extract_memories(
                                root_spec=spec, req=req, final_output=final_text,
                                memory=memory, emit=emit, parent_span_id=agent_span_id,
                                budget=budget,
                            )
                        return final_text

                    # Compile a bounded prompt view without mutating the authoritative transcript.
                    # The compiler replaces stale large tool outputs with artifact references.
                    compiled_messages, context_stats = context_compiler.compile(messages, workspace)
                    if context_stats.compacted_tool_results or context_stats.compacted_messages:
                        logger.debug(
                            "Compiled context for agent %s: %d -> %d chars (~%d tokens saved), %d tool results and %d messages compacted",
                            spec.id, context_stats.original_chars, context_stats.compiled_chars,
                            context_stats.estimated_tokens_saved, context_stats.compacted_tool_results,
                            context_stats.compacted_messages,
                        )

                    # LLM Call
                    turn = await self._execute_llm_turn(
                        spec=spec,
                        messages=compiled_messages,
                        tools=native_tool_specs,
                        parent_span_id=agent_span_id,
                        emit=emit,
                        budget=budget,
                        scenario=req.options.scenario,
                    )

                    messages.append(turn.message)
                    if depth == 0 and checkpoint:
                        await persist_state({
                            "messages": messages, "iterations": iterations,
                            "tool_call_history": tool_call_history,
                            "pending_tool_call_ids": [tc.id for tc in turn.tool_calls],
                        })

                    if not turn.tool_calls:
                        final_text = turn.text or ""
                        if depth == 0 and checkpoint:
                            await persist_state({"messages": messages, "iterations": iterations,
                                                 "tool_call_history": tool_call_history,
                                                 "pending_tool_call_ids": [], "final_output": final_text})
                        if depth == 0 and spec.memory_enabled and memory:
                            await self._extract_memories(
                                root_spec=spec, req=req, final_output=final_text,
                                memory=memory, emit=emit, parent_span_id=agent_span_id,
                                budget=budget,
                            )
                        return final_text

                    # Dispatch Tool Calls
                    tool_call_tuples = []
                    for tc in turn.tool_calls:
                        tool_key = f"{tc.name}:{json.dumps(tc.arguments, sort_keys=True)}"
                        tool_call_history.append(tool_key)

                        if tool_call_history.count(tool_key) >= 3:
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": "ERROR: Loop detected. You have called this exact tool with identical arguments 3 times. Provide a final response without tools.",
                            })
                            continue

                        tool_call_tuples.append(tc)

                    if not tool_call_tuples:
                        if depth == 0 and checkpoint:
                            await persist_state({"messages": messages, "iterations": iterations,
                                              "tool_call_history": tool_call_history,
                                              "pending_tool_call_ids": []})
                        continue

                    if depth == 0 and checkpoint:
                        await persist_state({"messages": messages, "iterations": iterations,
                                          "tool_call_history": tool_call_history,
                                          "pending_tool_call_ids": [tc.id for tc in tool_call_tuples]})

                    max_tasks = min(DEFAULT_MAX_SCHEDULED_TASKS, max(1, int(getattr(req.options, "max_tasks", DEFAULT_MAX_SCHEDULED_TASKS))))
                    scheduled_calls = tool_call_tuples[:max_tasks]
                    rejected_calls = tool_call_tuples[max_tasks:]
                    task_keys = {tc.id: f"call_{index}_{tc.id}" for index, tc in enumerate(scheduled_calls)}
                    plan = TaskPlan(
                        tasks={
                            task_keys[tc.id]: ScheduledTask(
                                task_id=task_keys[tc.id], agent_id=spec.id,
                                instruction=tc.name, max_attempts=1,
                            ) for tc in scheduled_calls
                        },
                        max_tasks=max_tasks,
                    )
                    plan.refresh_ready()
                    results_by_call: dict[str, str] = {
                        tc.id: f"ERROR: execution task limit exceeded ({max_tasks})."
                        for tc in rejected_calls
                    }
                    completed_tool_results: dict[str, str] = dict(results_by_call)
                    pending_call_ids = [tc.id for tc in scheduled_calls]
                    if depth == 0 and checkpoint:
                        await persist_state({
                            "messages": messages, "iterations": iterations,
                            "tool_call_history": tool_call_history,
                            "pending_tool_call_ids": pending_call_ids,
                            "completed_tool_results": completed_tool_results,
                        })

                    parallel_limit = (
                        max(1, int(getattr(req.options, "max_parallel_tool_calls", DEFAULT_MAX_PARALLEL_TOOL_CALLS)))
                        if req.options.parallel_tools else 1
                    )

                    while not plan.terminal:
                        claimed = plan.claim_ready(parallel_limit)
                        if not claimed:
                            break

                        async def execute_scheduled(task: ScheduledTask) -> tuple[str, str]:
                            tc = next(item for item in scheduled_calls if task_keys[item.id] == task.task_id)
                            try:
                                result_text = await self._execute_single_tool(
                                    tc=tc, spec=spec, graph=graph, tool_instances=tool_instances, req=req,
                                    parent_span_id=agent_span_id, depth=depth, emit=emit, cancel=cancel,
                                    approvals=approvals, workspace=workspace, tools_factory=tools_factory,
                                    memory=memory, lessons=lessons, intents=intents, run_history=run_history,
                                    budget=budget, active_agent_ids=agent_path,
                                    agent_revision_counts=agent_revision_counts, clock=clock,
                                )
                                return tc.id, result_text
                            except (BudgetExceededError, asyncio.CancelledError):
                                raise
                            except Exception as exc:
                                return tc.id, f"ERROR: tool crashed ({type(exc).__name__}: {exc})"

                        running = {
                            asyncio.create_task(execute_scheduled(task)): task
                            for task in claimed
                        }
                        while running:
                            done, _ = await asyncio.wait(
                                running, return_when=asyncio.FIRST_COMPLETED
                            )
                            for finished in done:
                                task = running.pop(finished)
                                try:
                                    call_id, result_text = finished.result()
                                except (BudgetExceededError, asyncio.CancelledError):
                                    for unfinished in running:
                                        unfinished.cancel()
                                    await asyncio.gather(*running, return_exceptions=True)
                                    raise
                                except Exception as exc:
                                    call_id = next(
                                        tc.id for tc in scheduled_calls
                                        if task_keys[tc.id] == task.task_id
                                    )
                                    result_text = f"ERROR: tool crashed ({type(exc).__name__}: {exc})"

                                results_by_call[call_id] = result_text
                                completed_tool_results[call_id] = result_text
                                if result_text.startswith("ERROR:"):
                                    plan.fail(task.task_id, result_text, retryable=False)
                                else:
                                    plan.complete(task.task_id)

                                # Persist each completion immediately. If a sibling tool
                                # is interrupted, completed work is retained and only the
                                # genuinely in-flight calls are marked uncertain.
                                pending_call_ids = [
                                    tc.id for tc in scheduled_calls
                                    if tc.id not in results_by_call
                                ]
                                if depth == 0 and checkpoint:
                                    await persist_state({
                                        "messages": messages, "iterations": iterations,
                                        "tool_call_history": tool_call_history,
                                        "pending_tool_call_ids": pending_call_ids,
                                        "completed_tool_results": completed_tool_results,
                                    })
                        plan.refresh_ready()

                    # Verify scheduler output coverage before returning control to the model.
                    # A scheduler edge case must become an explicit tool error, never a missing result.
                    for tc in scheduled_calls:
                        if tc.id not in results_by_call:
                            results_by_call[tc.id] = "ERROR: scheduler stopped before producing a result for this tool call."
                    for tc in tool_call_tuples:
                        messages.append({"role": "tool", "tool_call_id": tc.id,
                                         "content": results_by_call.get(tc.id, "ERROR: scheduler did not execute this task.")})
                    if depth == 0 and checkpoint:
                        await persist_state({"messages": messages, "iterations": iterations,
                                          "tool_call_history": tool_call_history,
                                          "pending_tool_call_ids": [],
                                          "completed_tool_results": {}})

                    continue

        finally:
            # agent_path is invocation-local; nothing is removed from shared state.
            pass

    async def _execute_llm_turn(
        self,
        spec: AgentSpec,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec],
        parent_span_id: str,
        emit: Emit,
        budget: BudgetTracker,
        scenario: str | None = None,
    ) -> LLMTurn:
        async with span(
            emit,
            kind="llm_call",
            name=None,
            parent_span_id=parent_span_id,
            data={
                "provider": spec.provider,
                "model": spec.model,
                "message_count": len(messages),
            },
        ) as llm_span_id:
            remaining = budget.remaining_seconds
            timeout_s = max(1, spec.params.timeout_s)
            if remaining is not None:
                timeout_s = min(timeout_s, remaining)
            if timeout_s <= 0:
                raise BudgetExceededError("Run deadline exhausted before LLM call.")
            reservation = budget.reserve_llm_call(estimated_tokens=max(0, spec.params.max_tokens or 0))
            try:
                async with asyncio.timeout(timeout_s):
                    if self.fake_llm:
                        turn = await self.fake_llm.complete(
                            messages=messages,
                            tools=[t.model_dump() for t in tools],
                            params=spec.params.model_dump(),
                        )
                    else:
                        try:
                            turn = await adapter_complete(
                                messages=messages, tools=tools, params=spec.params,
                                model=f"{spec.provider}/{spec.model}" if spec.provider else spec.model,
                            )
                        except LLMContextTooLong:
                            _trim_messages(messages)
                            turn = await adapter_complete(
                                messages=messages, tools=tools, params=spec.params,
                                model=f"{spec.provider}/{spec.model}" if spec.provider else spec.model,
                            )
            except TimeoutError as exc:
                budget.release_reservation(reservation)
                if budget.remaining_seconds is not None and budget.remaining_seconds <= 0:
                    raise BudgetExceededError("Run deadline exceeded during LLM call.") from exc
                raise LLMError(f"LLM call timed out after {timeout_s}s.") from exc
            except BaseException:
                budget.release_reservation(reservation)
                raise

            budget.record_llm_call(
                input_tokens=turn.usage.input_tokens,
                output_tokens=turn.usage.output_tokens,
                cache_read_tokens=turn.usage.cache_read_tokens,
                cost_usd=turn.cost_usd,
                reservation=reservation,
            )

            return turn

    async def _execute_single_tool(
        self,
        tc: ToolCall,
        spec: AgentSpec,
        graph: AgentGraph,
        tool_instances: dict[str, Any],
        req: RunRequest,
        parent_span_id: str,
        depth: int,
        emit: Emit,
        cancel: CancelToken,
        approvals: ApprovalGate,
        workspace: RunWorkspace,
        tools_factory: ToolFactory,
        memory: MemoryStore,
        lessons: LessonStore,
        intents: IntentStore,
        run_history: RunHistory,
        budget: BudgetTracker,
        active_agent_ids: set[str],
        agent_revision_counts: dict[str, int],
        clock: Clock,
    ) -> str:
        start_time = _clock_now(clock)
        # Account for the dispatch before span-start checkpointing so a crash
        # cannot lose the attempted tool-call count.
        budget.record_tool_call()
        async with span(
            emit,
            kind="tool_call",
            name=tc.name,
            parent_span_id=parent_span_id,
            data={
                "tool_name": tc.name,
                "tool_call_id": tc.id,
                "args": json.dumps(tc.arguments)[:2000],
            },
        ) as tool_span_id:
            child_link = next((c for c in spec.children if sanitize_tool_name(c.agent_id) == tc.name or c.agent_id == tc.name), None)
            if child_link:
                task_id = f"task_{tc.id}"
                child_instruction = tc.arguments.get("task", tc.arguments.get("instruction", tc.arguments.get("input", "")))

                directive = TaskDirective(
                    task_id=task_id,
                    sender_id=spec.id,
                    recipient_id=child_link.agent_id,
                    instruction=child_instruction,
                )

                try:
                    child_timeout = int(getattr(req.options, "tool_timeout_seconds", DEFAULT_TOOL_TIMEOUT_SECONDS))
                    remaining = budget.remaining_seconds
                    if remaining is not None:
                        child_timeout = min(child_timeout, remaining)
                    if child_timeout <= 0:
                        raise BudgetExceededError("Run deadline exhausted before child-agent execution.")
                    async with asyncio.timeout(child_timeout):
                        res_text = await self._run_agent(
                            agent_id=child_link.agent_id,
                            graph=graph,
                            req=req,
                            task=directive.instruction,
                            history=[],
                            history_summary="",
                            parent_span_id=tool_span_id,
                            depth=depth + 1,
                            emit=emit,
                            cancel=cancel,
                            approvals=approvals,
                            workspace=workspace,
                            tools_factory=tools_factory,
                            memory=memory,
                            lessons=lessons,
                            intents=intents,
                            run_history=run_history,
                            budget=budget,
                            active_agent_ids=active_agent_ids,
                            agent_revision_counts=agent_revision_counts,
                            clock=clock,
                        )

                    artifact_ref = workspace.write_result(task_id, res_text) if hasattr(workspace, "write_result") else None
                    uri = f"store://{artifact_ref.path}" if artifact_ref else f"store://.results/{task_id}.txt"

                    end_time = _clock_now(clock)
                    headline = res_text[:300].replace("\n", " ").strip() or "Child agent returned no summary."
                    child_status = (
                        "FAILED" if res_text.strip().startswith("ERROR:")
                        else "NEEDS_REVIEW" if not res_text.strip()
                        else "COMPLETED"
                    )
                    envelope = ClaimCheckEnvelope(
                        task_id=task_id,
                        sender_id=child_link.agent_id,
                        recipient_id=spec.id,
                        status=child_status,
                        summary=ClaimCheckSummary(
                            headline=headline,
                            flags_or_warnings=(
                                ["Child output indicates an execution error."]
                                if child_status == "FAILED"
                                else ["Child output is empty; review required."]
                                if child_status == "NEEDS_REVIEW"
                                else []
                            ),
                        ),
                        result_artifact_uri=uri,
                        temporal_telemetry={
                            "invoked_at_iso": start_time.isoformat(),
                            "completed_at_iso": end_time.isoformat(),
                            "duration_wall_clock_ms": int((end_time - start_time).total_seconds() * 1000),
                        },
                    )
                    return envelope.model_dump_json(indent=2)

                except (BudgetExceededError, asyncio.CancelledError):
                    raise
                except TimeoutError as exc:
                    if budget.remaining_seconds is not None and budget.remaining_seconds <= 0:
                        raise BudgetExceededError("Run deadline exceeded during child-agent execution.") from exc
                    return f"ERROR: sub-agent '{child_link.agent_id}' timed out after {child_timeout}s."
                except Exception as exc:
                    return f"ERROR: sub-agent '{child_link.agent_id}' failed: {exc}"

            tool_obj = tool_instances.get(tc.name)
            if not tool_obj:
                return f"ERROR: unknown tool '{tc.name}'. Available: {', '.join(tool_instances.keys())}"

            if tc.arguments_error:
                return f"ERROR: invalid arguments for '{tc.name}': {tc.arguments_error}"

            needed_perms = getattr(tool_obj, "permissions", set())
            allowed = await approvals.check(
                tool=tc.name,
                permissions=needed_perms,
                args_preview=json.dumps(tc.arguments)[:500],
                span_id=tool_span_id,
            )
            if not allowed:
                return "ERROR: the user denied this action"

            ctx = DummyToolContext(
                execution_id=req.execution_id,
                span_id=tool_span_id,
                agent_id=spec.id,
                workspace=workspace,
                cancel=cancel,
                config={},
            )

            try:
                input_cls = getattr(tool_obj, "Input", None)
                if input_cls:
                    args_inst = input_cls(**tc.arguments)
                else:
                    args_inst = tc.arguments

                remaining = budget.remaining_seconds
                timeout_s = int(getattr(req.options, "tool_timeout_seconds", DEFAULT_TOOL_TIMEOUT_SECONDS))
                if remaining is not None:
                    timeout_s = min(timeout_s, remaining)
                if timeout_s <= 0:
                    raise BudgetExceededError("Run deadline exhausted before tool execution.")
                async with budget.tool_semaphore:
                    for attempt in range(2):
                        try:
                            async with asyncio.timeout(timeout_s):
                                res: ToolResult = await tool_obj.run(args_inst, ctx)
                            break
                        except ToolError as retry_error:
                            # Retry only when the tool explicitly guarantees this failure
                            # is safe to retry; never infer idempotency from an error string.
                            if not retry_error.retryable or attempt == 1:
                                raise
                            logger.warning(
                                "Retrying explicitly retryable tool %s (attempt %d/2)",
                                tc.name, attempt + 2,
                            )
                if not isinstance(res, ToolResult):
                    return f"ERROR: tool '{tc.name}' returned an invalid result contract."
                if not res.ok:
                    return f"ERROR: tool '{tc.name}' reported failure: {res.content}"

                content = res.content
                if res.artifacts:
                    artifact_lines = [f"- {artifact.path}" for artifact in res.artifacts[:8]]
                    content += " | Artifacts produced: " + " | ".join(artifact_lines)
                if res.truncated:
                    continuation = f" Next offset: {res.next_offset}." if res.next_offset is not None else ""
                    content += f" | NOTE: tool output is truncated.{continuation}"

                saved_ref = None
                if len(content) > 1000 and hasattr(workspace, "write_result"):
                    saved_ref = workspace.write_result(tc.id, content)

                if len(content) > 6000:
                    head = content[:6000]
                    content = f"{head}\n...[truncated {len(content) - 6000} chars; full result saved at {saved_ref.path if saved_ref else '.results/' + tc.id + '.txt'}]"

                return content

            except BudgetExceededError:
                raise
            except asyncio.CancelledError:
                raise
            except TimeoutError as exc:
                if budget.remaining_seconds is not None and budget.remaining_seconds <= 0:
                    raise BudgetExceededError("Run deadline exceeded during tool execution.") from exc
                return f"ERROR: tool timed out after {timeout_s}s."
            except ToolError as te:
                return f"ERROR: {te.message}"
            except Exception as exc:
                return f"ERROR: tool crashed ({type(exc).__name__}: {exc})"

    def _assemble_tools(
        self,
        spec: AgentSpec,
        graph: AgentGraph,
        tools_factory: ToolFactory,
        memory: MemoryStore | None = None,
        intents: IntentStore | None = None,
        run_history: RunHistory | None = None,
    ) -> tuple[list[ToolSpec], dict[str, Any]]:
        tool_specs: list[ToolSpec] = []
        tool_instances: dict[str, Any] = {}

        raw_names = []
        for tb in spec.tools:
            raw_names.append(tb.name or tb.kind)
        for child in spec.children:
            raw_names.append(sanitize_tool_name(child.agent_id))

        raw_names.append("yield_time")
        if spec.memory_enabled and run_history:
            raw_names.append("recall_run")
        if intents:
            raw_names.extend(["intent_create", "intent_list", "intent_cancel"])

        deduped = dedupe_names(raw_names)
        idx = 0

        for tb in spec.tools:
            name = deduped[idx]
            idx += 1
            tool_inst = tools_factory.build(tb)
            tool_instances[name] = tool_inst

            schema = {}
            input_cls = getattr(tool_inst, "Input", None)
            if input_cls and hasattr(input_cls, "model_json_schema"):
                schema = input_cls.model_json_schema()

            tool_specs.append(
                ToolSpec(
                    name=name,
                    description=tb.description or getattr(tool_inst, "default_description", ""),
                    parameters=schema,
                )
            )

        for child in spec.children:
            name = deduped[idx]
            idx += 1
            child_spec = graph.agents.get(child.agent_id)
            desc = child.description or (child_spec.description if child_spec else f"Sub-agent {child.agent_id}")

            tool_specs.append(
                ToolSpec(
                    name=name,
                    description=desc,
                    parameters={
                        "type": "object",
                        "properties": {"task": {"type": "string", "description": "The task for the sub-agent"}},
                        "required": ["task"],
                    },
                )
            )

        # yield_time tool primitive
        yt_name = deduped[idx]
        idx += 1
        yt_inst = YieldTimeTool(intents)
        tool_instances[yt_name] = yt_inst
        tool_specs.append(ToolSpec(name=yt_name, description=yt_inst.default_description, parameters=yt_inst.Input.model_json_schema()))

        if spec.memory_enabled and run_history:
            from app.core.memory.episodic import RecallRunTool
            name = deduped[idx]
            idx += 1
            tool_inst = RecallRunTool(run_history)
            tool_instances[name] = tool_inst
            tool_specs.append(ToolSpec(name=name, description=tool_inst.default_description, parameters=tool_inst.Input.model_json_schema()))

        if intents:
            from app.core.memory.intents import IntentCancelTool, IntentCreateTool, IntentListTool
            for ToolCls in (IntentCreateTool, IntentListTool, IntentCancelTool):
                name = deduped[idx]
                idx += 1
                tool_inst = ToolCls(intents)
                tool_instances[name] = tool_inst
                tool_specs.append(ToolSpec(name=name, description=tool_inst.default_description, parameters=tool_inst.Input.model_json_schema()))

        return tool_specs, tool_instances

    async def _force_text_turn(
        self,
        spec: AgentSpec,
        messages: list[dict[str, Any]],
        parent_span_id: str,
        emit: Emit,
        budget: BudgetTracker,
    ) -> str:
        messages.append({
            "role": "user",
            "content": "You have reached the maximum tool iterations limit. Please summarize your work and provide a final answer now without using any tools.",
        })
        turn = await self._execute_llm_turn(spec, messages, [], parent_span_id, emit, budget)
        return turn.text or ""

    async def _extract_memories(
        self,
        root_spec: AgentSpec,
        req: RunRequest,
        final_output: str,
        memory: MemoryStore,
        emit: Emit,
        parent_span_id: str | None,
        budget: BudgetTracker,
    ) -> None:
        if not memory:
            return
        async with span(
            emit,
            kind="llm_call",
            name="memory_extract",
            parent_span_id=parent_span_id,
            data={"provider": root_spec.provider, "model": "fast"},
        ) as extract_span_id:

            user_msgs = [req.task] + [
                m.content if hasattr(m, "content") else m.get("content", "")
                for m in req.history
                if (getattr(m, "role", None) or m.get("role")) == "user"
            ]

            llm_fn = self.fake_llm.complete if self.fake_llm else None
            await extract_and_store_memories(
                spec=root_spec,
                user_messages=user_msgs,
                final_output=final_output,
                execution_id=req.execution_id,
                store=memory,
                llm_complete_fn=llm_fn,
            )


def _find_recovered_tool_error(messages: list[dict[str, Any]]) -> tuple[str, str] | None:
    """Return one earlier tool error only when a later tool result succeeded."""
    first_error: str | None = None
    recovered_output = ""
    for message in messages:
        if message.get("role") != "tool":
            continue
        content = str(message.get("content", ""))
        if content.startswith("ERROR:") and first_error is None:
            first_error = content[6:].strip()[:500]
        elif first_error and content and not content.startswith("ERROR:"):
            recovered_output = content[:500]
            return first_error, recovered_output
    return None


def _build_self_model(
    *,
    spec: AgentSpec,
    graph: AgentGraph,
    req: RunRequest,
    budget: BudgetTracker,
    skill_manifest: SkillManifest | None,
    depth: int,
) -> str:
    """Build a compact, current-run description from runtime configuration."""
    selected_skill = None
    if skill_manifest is not None:
        selected_skill = {
            "name": skill_manifest.name,
            "required_binaries": list(skill_manifest.metadata.requires_bins),
            "required_environment_variables": list(skill_manifest.metadata.requires_env),
            "declared_tools": list(skill_manifest.metadata.tools),
        }
    max_seconds = req.options.budget.max_seconds
    return json.dumps({
        "agent": {"id": spec.id, "name": spec.name, "depth": depth},
        "configured_tool_bindings": [
            {"name": item.name, "kind": item.kind} for item in spec.tools
        ],
        "delegation_targets": [
            {"agent_id": child.agent_id, "description": child.description or ""}
            for child in spec.children if child.agent_id in graph.agents
        ],
        "memory_enabled": bool(spec.memory_enabled),
        "lessons_enabled": bool(spec.lessons_enabled),
        "selected_skill_and_declared_prerequisites": selected_skill,
        "constraints": {
            "max_depth": req.options.max_depth,
            "remaining_depth": max(0, req.options.max_depth - depth),
            "remaining_seconds": max(0.0, max_seconds - budget.elapsed_seconds) if max_seconds else None,
            "max_tokens_per_model_call": spec.params.max_tokens,
            "parallel_tools_enabled": bool(req.options.parallel_tools),
            "max_parallel_tool_calls": getattr(req.options, "max_parallel_tool_calls", DEFAULT_MAX_PARALLEL_TOOL_CALLS),
            "approval_gate_present": True,
        },
        "accuracy_note": (
            "Tool bindings and skill prerequisites describe configured state, not guaranteed "
            "external availability. Do not claim a capability or permission is operational "
            "unless the current execution verifies it."
        ),
    }, ensure_ascii=False, separators=(",", ":"))


def _trim_messages(messages: list[dict[str, Any]]) -> None:
    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    if len(tool_msgs) > 3:
        for m in tool_msgs[:-3]:
            m["content"] = "[tool output trimmed to fit context window]"


class DummyToolContext:
    def __init__(self, execution_id: str, span_id: str, agent_id: str, workspace: Any, cancel: Any, config: dict):
        self.execution_id = execution_id
        self.span_id = span_id
        self.agent_id = agent_id
        self.workspace = workspace
        self.cancel = cancel
        self.config = config


def _clock_now(clock: Clock) -> datetime:
    """Return an aware UTC timestamp from the injected clock."""
    value = clock()
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Injected clock must return a timezone-aware datetime.")
    return value.astimezone(timezone.utc)


def _fingerprint(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
