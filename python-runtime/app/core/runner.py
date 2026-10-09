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
from app.core.scheduler import ScheduledTask, TaskPlan
from app.core.claim_check import ClaimCheckEnvelope, ClaimCheckSummary, TaskDirective
from app.core.lessons import format_lessons_block
from app.core.llm.adapter import complete as adapter_complete
from app.core.llm.fake import FakeLLM
from app.core.llm.pricing import get_context_window
from app.core.llm.types import LLMContextTooLong, LLMError, LLMParams, LLMTurn, ToolCall, ToolSpec, Usage
from app.core.memory.episodic import build_recent_runs_block
from app.core.memory.extractor import extract_and_store_memories
from app.core.memory.recall import recall_memories
from app.core.prompt_builder import build_system_prompt
from app.core.skills.types import SkillManifest
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

        try:
            final_output = await self._run_agent(
                agent_id=graph.root_id,
                graph=graph,
                req=req,
                task=req.task,
                history=list(req.history),
                history_summary=req.history_summary,
                parent_span_id=None,
                depth=0,
                emit=emit,
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
            )

            if root_spec.memory_enabled and memory:
                await self._extract_memories(
                    root_spec=root_spec,
                    req=req,
                    final_output=final_output,
                    memory=memory,
                    emit=emit,
                    parent_span_id=None,
                    budget=budget,
                )

            return RunResult(
                status="completed",
                final_output=final_output,
                totals=budget.totals,
            )

        except BudgetExceededError as exc:
            return RunResult(
                status="budget_exceeded",
                error=str(exc),
                totals=budget.totals,
            )
        except asyncio.CancelledError:
            return RunResult(
                status="cancelled",
                error="Run was cancelled by user.",
                totals=budget.totals,
            )
        except Exception as exc:
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
    ) -> str:
        cancel.raise_if_cancelled()
        budget.check_limits()

        if agent_id in active_agent_ids:
            raise RuntimeError(f"Cycle detected in agent graph for agent '{agent_id}'")
        if depth > req.options.max_depth:
            raise RuntimeError(f"Maximum delegation depth reached ({depth} > {req.options.max_depth})")
        # Copy the ancestry per invocation: sibling invocations of the same agent definition
        # must not mutate or observe one another's active path.
        agent_path = set(active_agent_ids)
        agent_path.add(agent_id)
        spec = graph.agents[agent_id]

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
            ) as agent_span_id:

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

                # 2. Recent problem runs
                recent_runs_block = ""
                if req.options.memory.episodic and run_history and depth == 0:
                    recent_runs_block = await build_recent_runs_block(run_history, spec.id)

                # 3. Due reminders
                reminders_block = ""
                if req.options.memory.intents and intents and depth == 0:
                    now_utc = _clock_now(clock)
                    due_intents = await intents.due_for_run(spec.id, now_utc)
                    if due_intents:
                        reminders_block = "\n".join(f"- {i.text}" for i in due_intents)
                        await intents.mark_fired([i.id for i in due_intents], now_utc)

                # 4. Lessons
                lessons_block = ""
                if spec.lessons_enabled and lessons:
                    lessons_block = await format_lessons_block(lessons, spec.id)

                # 5. Temporal Context
                now_dt = _clock_now(clock)
                temporal_context = {
                    "current_time_iso": now_dt.isoformat(),
                    "epoch_timestamp_ms": int(now_dt.timestamp() * 1000),
                    "session_elapsed_ms": int(budget.elapsed_seconds * 1000),
                    "remaining_budget_ms": int((req.options.budget.max_seconds - budget.elapsed_seconds) * 1000) if req.options.budget.max_seconds else None,
                }

                # 6. Build system prompt
                system_prompt = build_system_prompt(
                    spec=spec,
                    memory_block=memory_block,
                    reminders_block=reminders_block,
                    recent_runs_block=recent_runs_block,
                    lessons_block=lessons_block,
                    history_summary_block=history_summary,
                    skill_manifest=skill_manifest,
                    temporal_context=temporal_context,
                )

                messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
                for msg in history:
                    messages.append({"role": msg.role if hasattr(msg, "role") else msg["role"], "content": msg.content if hasattr(msg, "content") else msg["content"]})
                messages.append({"role": "user", "content": task})

                # 7. Assemble tools
                native_tool_specs, tool_instances = self._assemble_tools(spec, graph, tools_factory, memory, intents, run_history)

                iterations = 0
                tool_call_history: list[str] = []

                while True:
                    cancel.raise_if_cancelled()
                    budget.check_limits()
                    iterations += 1

                    if iterations > req.options.max_iterations:
                        return await self._force_text_turn(
                            spec, messages, agent_span_id, emit, budget
                        )

                    # LLM Call
                    turn = await self._execute_llm_turn(
                        spec=spec,
                        messages=messages,
                        tools=native_tool_specs,
                        parent_span_id=agent_span_id,
                        emit=emit,
                        budget=budget,
                        scenario=req.options.scenario,
                    )

                    messages.append(turn.message)

                    if not turn.tool_calls:
                        return turn.text or ""

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
                        continue

                    if req.options.parallel_tools and len(tool_call_tuples) > 1:
                        results = await asyncio.gather(
                            *[
                                self._execute_single_tool(
                                    tc=tc,
                                    spec=spec,
                                    graph=graph,
                                    tool_instances=tool_instances,
                                    req=req,
                                    parent_span_id=agent_span_id,
                                    depth=depth,
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
                                    active_agent_ids=agent_path,
                                    agent_revision_counts=agent_revision_counts,
                                    clock=clock,
                                )
                                for tc in tool_call_tuples
                            ],
                            return_exceptions=True,
                        )
                        for tc, res in zip(tool_call_tuples, results):
                            if isinstance(res, BudgetExceededError):
                                raise res
                            if isinstance(res, asyncio.CancelledError):
                                raise res
                            if isinstance(res, Exception):
                                content = f"ERROR: tool crashed ({type(res).__name__}: {res})"
                            else:
                                content = res
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": content,
                            })
                    else:
                        for tc in tool_call_tuples:
                            try:
                                content = await self._execute_single_tool(
                                    tc=tc,
                                    spec=spec,
                                    graph=graph,
                                    tool_instances=tool_instances,
                                    req=req,
                                    parent_span_id=agent_span_id,
                                    depth=depth,
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
                                    active_agent_ids=agent_path,
                                    agent_revision_counts=agent_revision_counts,
                                    clock=clock,
                                )
                            except (BudgetExceededError, asyncio.CancelledError):
                                raise
                            except Exception as exc:
                                content = f"ERROR: tool crashed ({type(exc).__name__}: {exc})"

                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": content,
                            })

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
            budget.record_tool_call()

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
                    child_timeout = req.options.tool_timeout_seconds
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
                    headline = res_text[:300].replace("\n", " ").strip()
                    envelope = ClaimCheckEnvelope(
                        task_id=task_id,
                        sender_id=child_link.agent_id,
                        recipient_id=spec.id,
                        status="COMPLETED",
                        summary=ClaimCheckSummary(headline=headline),
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
                timeout_s = req.options.tool_timeout_seconds
                if remaining is not None:
                    timeout_s = min(timeout_s, remaining)
                if timeout_s <= 0:
                    raise BudgetExceededError("Run deadline exhausted before tool execution.")
                async with budget.tool_semaphore:
                    async with asyncio.timeout(timeout_s):
                        res: ToolResult = await tool_obj.run(args_inst, ctx)
                content = res.content

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
