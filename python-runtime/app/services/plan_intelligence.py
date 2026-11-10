"""Cheap-LLM interpretation and deterministic reconciliation for hierarchical task plans.

TaskState.state_json holds the current hierarchy; TaskStateEvent is its append-only
history. The interpreter can suggest structure, but it cannot rewrite the immutable
root objective, silently accept design decisions, or mark work complete.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import models
from app.core.llm.adapter import complete
from app.core.llm.model_names import litellm_model
from app.core.llm.types import LLMParams
from app.db import SessionLocal
from app.infra.paths import data_dir

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "enabled": False,
    "provider": "gemini",
    "model": "gemini-2.5-flash-lite",
    "max_tokens": 1800,
    "temperature": 0,
}
_ALLOWED_PROVIDERS = {
    "anthropic", "openai", "gemini", "google", "deepseek", "mistral",
    "groq", "xai", "openrouter", "venice", "ollama",
}
_ALLOWED_NODE_TYPES = {"goal", "phase", "subgoal", "task", "milestone"}
_MAX_NODES = 500
_MAX_CONTEXT_CHARS = 4200


def _config_path() -> Path:
    return data_dir() / "plan_memory_settings.json"


def _valid_model_config(provider: Any, model: Any) -> bool:
    return (
        isinstance(provider, str)
        and provider in _ALLOWED_PROVIDERS
        and isinstance(model, str)
        and 1 <= len(model.strip()) <= 160
        and not any(char.isspace() for char in model)
        and bool(re.fullmatch(r"[A-Za-z0-9_.:/-]+", model))
    )


def load_plan_memory_settings() -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    try:
        stored = json.loads(_config_path().read_text("utf-8"))
        if isinstance(stored, dict):
            if _valid_model_config(stored.get("provider"), stored.get("model")):
                config["provider"] = stored["provider"]
                config["model"] = stored["model"]
            if isinstance(stored.get("enabled"), bool):
                config["enabled"] = stored["enabled"]
    except (OSError, ValueError, TypeError):
        pass
    return config


def save_plan_memory_settings(payload: dict[str, Any]) -> dict[str, Any]:
    current = load_plan_memory_settings()
    enabled = payload.get("enabled", current["enabled"])
    provider = payload.get("provider", current["provider"])
    model = payload.get("model", current["model"])
    if not isinstance(enabled, bool) or not _valid_model_config(provider, model):
        raise ValueError("Choose a supported provider and a valid model identifier.")
    result = {"enabled": enabled, "provider": provider, "model": model}
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return result


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_object(text: str) -> dict[str, Any]:
    value = (text or "").strip()
    if value.startswith("```"):
        value = re.sub(r"^\`\`\`(?:json)?\s*|\s*\`\`\`$", "", value, flags=re.I)
    start, end = value.find("{"), value.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("The memory model did not return a JSON object.")
    parsed = json.loads(value[start:end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("The memory model response must be a JSON object.")
    return parsed


def _normal_text(value: Any, limit: int = 280) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit].strip()


def _user_evidence_is_exact(evidence: str, user_text: str) -> bool:
    return bool(evidence and evidence.casefold() in user_text.casefold())


def _would_create_dependency_cycle(
    dependencies: list[dict[str, Any]],
    node_id: str,
    depends_on_id: str,
) -> bool:
    adjacency: dict[str, list[str]] = {}
    for edge in dependencies:
        if isinstance(edge, dict):
            adjacency.setdefault(str(edge.get("node_id")), []).append(str(edge.get("depends_on_id")))
    pending = [depends_on_id]
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if current == node_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        pending.extend(adjacency.get(current, []))
    return False


def _status_matches_evidence(status: str, evidence: str) -> bool:
    patterns = {
        "active": r"\b(resume|continue|restart|reactivate|proceed)\b",
        "blocked": r"\b(blocked|stuck|cannot proceed|can't proceed|unable to continue)\b",
        "paused": r"\b(pause|paused|hold|defer)\b",
        "superseded": r"\b(replace|supersede|discard|cancel|no longer|instead|switch from)\b",
    }
    return bool(re.search(patterns.get(status, r"(?!)"), evidence, re.I))


def _apply_interpretation(
    task_state_id: str,
    proposal: dict[str, Any],
    user_text: str,
    evidence_text: str | None = None,
) -> dict[str, Any]:
    now = _now()
    with SessionLocal() as db:
        row = db.get(models.TaskState, task_state_id)
        if row is None:
            return {"applied": False, "reason": "task_missing"}
        state = dict(row.state_json or {})
        plan = dict(state.get("plan") or {})
        nodes = list(plan.get("nodes") or [])
        decisions = list(plan.get("decisions") or [])
        constraints = list(plan.get("constraints") or [])
        dependencies = list(plan.get("dependencies") or [])
        existing = {str(item.get("id")): item for item in nodes if isinstance(item, dict)}
        ref_to_id = {"root": task_state_id, **{node_id: node_id for node_id in existing}}
        changed = 0
        applied_changes: list[dict[str, Any]] = []
        root_summary = _normal_text(proposal.get("root_summary"), 1800)
        if root_summary and not plan.get("root_summary"):
            plan["root_summary"] = root_summary
            applied_changes.append({"kind": "root_summary_set", "text": root_summary})
            changed += 1
        additions = proposal.get("nodes") if isinstance(proposal.get("nodes"), list) else []
        for item in additions[:12]:
            if not isinstance(item, dict) or len(nodes) >= _MAX_NODES:
                continue
            title = _normal_text(item.get("title"), 120)
            objective = _normal_text(item.get("objective"), 500)
            node_type = item.get("type")
            if not title or node_type not in _ALLOWED_NODE_TYPES:
                continue
            evidence = _normal_text(item.get("evidence"), 500)
            source = item.get("source")
            parent_ref = _normal_text(item.get("parent_ref"), 80) or "root"
            parent_id = ref_to_id.get(parent_ref)
            if not parent_id:
                continue
            node_ref = _normal_text(item.get("ref"), 80)
            if node_ref and node_ref in ref_to_id:
                continue
            # User-authored goals/requirements require a verbatim quote. Agent plans
            # may be recorded as proposals, but cannot masquerade as user decisions.
            if source == "user" and not _user_evidence_is_exact(evidence, user_text):
                continue
            if source != "user":
                source = "agent"
            duplicate = next((n for n in nodes if n.get("parent_id") == parent_id and
                              _normal_text(n.get("title"), 120).casefold() == title.casefold()), None)
            if duplicate:
                continue
            node = {
                "id": str(uuid.uuid4()),
                "parent_id": parent_id,
                "type": node_type,
                "title": title,
                "objective": objective,
                "status": "active",
                "source": source,
                "evidence": evidence if source == "user" else "",
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "version": 1,
            }
            nodes.append(node)
            existing[node["id"]] = node
            if node_ref:
                ref_to_id[node_ref] = node["id"]
            applied_changes.append({"kind": "node_added", "node": node})
            changed += 1

        for item in (proposal.get("dependencies") if isinstance(proposal.get("dependencies"), list) else [])[:16]:
            if not isinstance(item, dict):
                continue
            node_ref = _normal_text(item.get("node_ref"), 80)
            depends_on_ref = _normal_text(item.get("depends_on_ref"), 80)
            node_id = ref_to_id.get(node_ref)
            depends_on_id = ref_to_id.get(depends_on_ref)
            if not node_id or not depends_on_id or node_id == depends_on_id:
                continue
            if _would_create_dependency_cycle(dependencies, node_id, depends_on_id):
                continue
            if any(
                edge.get("node_id") == node_id and edge.get("depends_on_id") == depends_on_id
                for edge in dependencies if isinstance(edge, dict)
            ):
                continue
            edge = {
                "id": str(uuid.uuid4()),
                "node_id": node_id,
                "depends_on_id": depends_on_id,
                "reason": _normal_text(item.get("reason"), 240),
                "source": "agent",
                "created_at": now.isoformat(),
            }
            dependencies.append(edge)
            applied_changes.append({"kind": "dependency_added", "dependency": edge})
            changed += 1

        for item in (proposal.get("node_updates") if isinstance(proposal.get("node_updates"), list) else [])[:12]:
            if not isinstance(item, dict):
                continue
            node_id = _normal_text(item.get("id"), 80)
            status = item.get("status")
            evidence = _normal_text(item.get("evidence"), 500)
            node = existing.get(node_id)
            if not node or status not in {"active", "blocked", "paused", "superseded"}:
                continue
            evidence_source = user_text if node.get("source") == "user" else (evidence_text or user_text)
            if not _user_evidence_is_exact(evidence, evidence_source) or not _status_matches_evidence(status, evidence):
                continue
            if node.get("status") != status:
                previous_status = node.get("status")
                node["status"] = status
                node["updated_at"] = now.isoformat()
                node["version"] = int(node.get("version", 1)) + 1
                applied_changes.append({
                    "kind": "node_status_changed",
                    "node_id": node_id,
                    "from": previous_status,
                    "to": status,
                    "evidence": evidence,
                })
                changed += 1

        for item in (proposal.get("decisions") if isinstance(proposal.get("decisions"), list) else [])[:12]:
            if not isinstance(item, dict):
                continue
            statement = _normal_text(item.get("text"), 400)
            evidence = _normal_text(item.get("evidence"), 500)
            if not statement:
                continue
            user_confirmed = (
                item.get("authority") == "user"
                and _user_evidence_is_exact(evidence, user_text)
                and statement.casefold() in evidence.casefold()
            )
            status = "accepted" if user_confirmed else "proposed"
            supersedes = _normal_text(item.get("supersedes"), 80)
            if user_confirmed and supersedes in {d.get("id") for d in decisions if isinstance(d, dict) and d.get("status") == "accepted"}:
                for prior in decisions:
                    if isinstance(prior, dict) and prior.get("id") == supersedes and prior.get("status") == "accepted":
                        prior["status"] = "superseded"
                        prior["superseded_by"] = statement
                        applied_changes.append({"kind": "decision_superseded", "decision_id": supersedes, "replacement": statement})
            if any(d.get("text", "").casefold() == statement.casefold() and d.get("status") == status
                   for d in decisions if isinstance(d, dict)):
                continue
            decision = {
                "id": str(uuid.uuid4()),
                "text": statement,
                "status": status,
                "authority": "user" if user_confirmed else "agent",
                "evidence": evidence if user_confirmed else "",
                "created_at": now.isoformat(),
            }
            decisions.append(decision)
            applied_changes.append({"kind": "decision_added", "decision": decision})
            changed += 1

        for item in (proposal.get("constraints") if isinstance(proposal.get("constraints"), list) else [])[:8]:
            if not isinstance(item, dict):
                continue
            statement = _normal_text(item.get("text"), 300)
            evidence = _normal_text(item.get("evidence"), 500)
            if statement and _user_evidence_is_exact(evidence, user_text) and statement.casefold() in evidence.casefold() and not any(
                c.get("text", "").casefold() == statement.casefold()
                for c in constraints if isinstance(c, dict)
            ):
                constraint = {
                    "id": str(uuid.uuid4()), "text": statement,
                    "evidence": evidence, "created_at": now.isoformat(),
                }
                constraints.append(constraint)
                applied_changes.append({"kind": "constraint_added", "constraint": constraint})
                changed += 1

        if changed == 0:
            return {"applied": False, "reason": "no_valid_changes"}
        plan.update({
            "schema_version": 1,
            "root_summary": plan.get("root_summary", ""),
            "nodes": nodes[-_MAX_NODES:],
            "decisions": decisions[-80:],
            "constraints": constraints[-80:],
            "dependencies": dependencies[-300:],
            "updated_at": now.isoformat(),
        })
        state["plan"] = plan
        row.state_json = state
        row.version += 1
        row.updated_at = now
        db.add(models.TaskStateEvent(
            id=models._uuid(),
            task_state_id=row.id,
            event_type="plan_memory_updated",
            content=_normal_text(proposal.get("summary"), 500) or f"Plan memory updated ({changed} changes).",
            payload={
                "schema_version": 1,
                "change_count": changed,
                "node_count": len(nodes),
                "decision_count": len(decisions),
                "constraint_count": len(constraints),
                "dependency_count": len(dependencies),
                "model": proposal.get("_model", ""),
                "changes": applied_changes,
            },
            created_at=now,
        ))
        db.commit()
        try:
            from app.services.task_memory import _write_projection
            _write_projection(db, row)
        except Exception:
            logger.exception("Could not refresh task-memory projection after plan update")
        return {"applied": True, "changes": changed, "nodes": len(nodes)}


def _budget_allows_memory_call(budget: Any, prompt: str, max_output_tokens: int) -> bool:
    """Reserve execution budget so optional memory work cannot starve the main agent."""
    if budget is None:
        return True
    spec = budget.spec
    totals = budget.totals
    if spec.max_llm_calls is not None and totals.llm_calls + 1 >= spec.max_llm_calls:
        return False
    if spec.max_total_tokens is not None:
        used = totals.input_tokens + totals.output_tokens
        estimated = max(1, len(prompt) // 4) + max_output_tokens + 1000
        if used + estimated >= spec.max_total_tokens:
            return False
    if spec.max_cost_usd is not None:
        if (totals.cost_usd or 0.0) + 0.01 >= spec.max_cost_usd:
            return False
    if spec.max_seconds is not None and budget.elapsed_seconds + 12 >= spec.max_seconds:
        return False
    return True


def _should_interpret(message: str) -> bool:
    text = message.strip()
    if len(text) < 8:
        return False
    normalized = re.sub(r"[^a-z ]", "", text.casefold()).strip()
    if normalized in {"hi", "hello", "hey", "hi there", "hello there", "hey there", "ok", "okay", "thanks", "thank you", "good morning", "good afternoon", "good evening"}:
        return False
    signal = re.search(
        r"\b(remember|goal|objective|plan|phase|step|subgoal|constraint|requirement|"
        r"decision|instead|actually|change|correction|don't|do not|must|should|use|avoid|prefer|choose|selected|switch|replace|rather than|never|always|require|requires|ensure|keep|remove|add|we decided|"
        r"completed|finished|blocked|failed|error|continue|next|first|then|"
        r"architecture|design|build|implement|test|verify|reject|replace)\b",
        text, re.I,
    )
    return len(text) >= 70 or bool(signal)


async def update_plan_memory(
    task_state_id: str | None,
    user_message: str,
    history: list[Any] | None = None,
    budget: Any = None,
) -> dict[str, Any]:
    """Interpret one meaningful user turn and apply only reconciled, evidence-backed changes."""
    if not task_state_id or not _should_interpret(user_message):
        return {"applied": False, "reason": "not_meaningful"}
    config = load_plan_memory_settings()
    if not config["enabled"]:
        return {"applied": False, "reason": "disabled"}

    with SessionLocal() as db:
        row = db.get(models.TaskState, task_state_id)
        if row is None:
            return {"applied": False, "reason": "task_missing"}
        current_plan = dict((row.state_json or {}).get("plan") or {})
        compact_nodes = [
            {key: node.get(key) for key in ("id", "parent_id", "type", "title", "objective", "status", "source")}
            for node in (current_plan.get("nodes") or [])[-50:] if isinstance(node, dict)
        ]
        compact_dependencies = [
            {key: edge.get(key) for key in ("node_id", "depends_on_id", "reason")}
            for edge in (current_plan.get("dependencies") or [])[-40:] if isinstance(edge, dict)
        ]
        compact_decisions = [
            {key: item.get(key) for key in ("id", "text", "status", "authority")}
            for item in (current_plan.get("decisions") or [])[-30:] if isinstance(item, dict)
        ]
        objective = row.original_objective

    history_lines = []
    for msg in (history or [])[-6:]:
        role = getattr(msg, "role", None) or (msg.get("role") if isinstance(msg, dict) else "")
        content = getattr(msg, "content", None) or (msg.get("content", "") if isinstance(msg, dict) else "")
        if role in {"user", "assistant", "tool"} and isinstance(content, str) and content.strip():
            history_lines.append(f"{role}: {content[:700]}")
    recent_history = "\n".join(history_lines)[-3000:]
    current_message_section = (
        "(same as the immutable root objective above)"
        if user_message.strip() == (objective or "").strip()
        else user_message[:8000]
    )
    prompt = (
        "You are AgentForge's low-cost project-plan memory interpreter. Return JSON only. "
        "Maintain a hierarchical plan for a long-running project. The immutable root objective is "
        "authoritative. root_summary must concisely preserve the root objective and its major requirements only; never fold later corrections into it. Extract important requirements, constraints, and decisions rather than a generic summary. Distinguish user-stated goals/constraints/decisions from agent-generated "
        "execution-plan ideas. Errors are evidence/blockers, never new goals. Do not mark work complete; "
        "completion requires verified execution evidence elsewhere. Never invent user approval. "
        "Only label source='user' or authority='user' when evidence is an exact substring of the current "
        "user message. For accepted decisions/constraints, their text must appear verbatim inside that quote. "
        "User-owned node status changes require current-user evidence; agent-owned nodes may change status "
        "using exact evidence from recent tool results or conversation history. Agent-generated phases/tasks "
        "should use source='agent'. Add only meaningful deltas; "
        "avoid duplicating existing nodes. Node parent_ref must be 'root', an existing node id, or an earlier node ref from this same response. Include a unique ref on new parent nodes before their children. "
        "Allowed node types: goal, phase, subgoal, task, milestone. Keep each item concise.\n"
        "JSON schema: {summary:string,root_summary:string,nodes:[{ref,type,title,objective,parent_ref,source,evidence}],"
        "decisions:[{text,authority,evidence,supersedes}],constraints:[{text,evidence}],dependencies:[{node_ref,depends_on_ref,reason}],node_updates:[{id,status,evidence}]}\n\n"
        f"ROOT OBJECTIVE (immutable): {(objective or '')[:8000]}\n"
        f"CURRENT HIERARCHY: {json.dumps(compact_nodes, ensure_ascii=False)[:4000]}\n"
        f"CURRENT DECISIONS: {json.dumps(compact_decisions, ensure_ascii=False)[:1800]}\n"
        f"CURRENT DEPENDENCIES: {json.dumps(compact_dependencies, ensure_ascii=False)[:1400]}\n"
        f"RECENT CONVERSATION: {recent_history}\n"
        f"CURRENT USER MESSAGE: {current_message_section}"
    )
    if not _budget_allows_memory_call(budget, prompt, config["max_tokens"]):
        return {"applied": False, "reason": "run_budget_reserved_for_execution"}
    try:
        model_name = litellm_model(config["provider"], config["model"])
        turn = await complete(
            messages=[
                {"role": "system", "content": "Extract structured plan-memory deltas. Output valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            params=LLMParams(timeout_s=12, temperature=0, max_tokens=config["max_tokens"]),
            model=model_name,
            provider=config["provider"],
            max_retries=0,
        )
        if budget is not None:
            budget.record_llm_call(
                input_tokens=turn.usage.input_tokens,
                output_tokens=turn.usage.output_tokens,
                cache_read_tokens=turn.usage.cache_read_tokens,
                cost_usd=turn.cost_usd,
            )
        proposal = _json_object(turn.text or "")
        proposal["_model"] = model_name
        evidence_text = user_message + "\n" + recent_history
        return await asyncio.to_thread(
            _apply_interpretation, task_state_id, proposal, user_message, evidence_text
        )
    except Exception as exc:
        logger.warning("Plan-memory interpretation skipped (%s): %s", type(exc).__name__, str(exc)[:240])
        return {"applied": False, "reason": "interpreter_error"}


def rebuild_plan_from_history(task_state_id: str) -> dict[str, Any]:
    """Reconstruct the current hierarchy from its append-only task events."""
    with SessionLocal() as db:
        row = db.get(models.TaskState, task_state_id)
        if row is None:
            return {"rebuilt": False, "reason": "task_missing"}
        events = (
            db.query(models.TaskStateEvent)
            .filter(models.TaskStateEvent.task_state_id == task_state_id)
            .order_by(models.TaskStateEvent.created_at.asc(), models.TaskStateEvent.id.asc())
            .all()
        )
        plan: dict[str, Any] = {
            "schema_version": 1,
            "root_summary": "",
            "nodes": [],
            "decisions": [],
            "constraints": [],
            "dependencies": [],
        }
        nodes_by_id: dict[str, dict[str, Any]] = {}
        decisions_by_id: dict[str, dict[str, Any]] = {}
        for event in events:
            payload = event.payload if isinstance(event.payload, dict) else {}
            if event.event_type == "plan_memory_updated":
                for change in payload.get("changes", []):
                    if not isinstance(change, dict):
                        continue
                    kind = change.get("kind")
                    if kind == "root_summary_set":
                        plan["root_summary"] = _normal_text(change.get("text"), 1800)
                    elif kind == "node_added":
                        node = change.get("node")
                        if isinstance(node, dict) and node.get("id"):
                            nodes_by_id[str(node["id"])] = dict(node)
                    elif kind == "node_status_changed":
                        node = nodes_by_id.get(str(change.get("node_id")))
                        if node:
                            node["status"] = change.get("to", node.get("status"))
                            node["updated_at"] = event.created_at.isoformat()
                            node["version"] = int(node.get("version", 1)) + 1
                    elif kind == "decision_added":
                        decision = change.get("decision")
                        if isinstance(decision, dict) and decision.get("id"):
                            decisions_by_id[str(decision["id"])] = dict(decision)
                    elif kind == "decision_superseded":
                        decision = decisions_by_id.get(str(change.get("decision_id")))
                        if decision:
                            decision["status"] = "superseded"
                            decision["superseded_by"] = change.get("replacement", "")
                    elif kind == "constraint_added":
                        constraint = change.get("constraint")
                        if isinstance(constraint, dict) and constraint.get("id"):
                            plan["constraints"].append(dict(constraint))
                    elif kind == "dependency_added":
                        dependency = change.get("dependency")
                        if isinstance(dependency, dict) and dependency.get("id"):
                            plan["dependencies"].append(dict(dependency))
            elif event.event_type == "agent_state_update":
                for decision in payload.get("plan_decisions_added", []):
                    if isinstance(decision, dict) and decision.get("id"):
                        decisions_by_id[str(decision["id"])] = dict(decision)
                for constraint in payload.get("plan_constraints_added", []):
                    if isinstance(constraint, dict) and constraint.get("id"):
                        plan["constraints"].append(dict(constraint))
                for node in payload.get("plan_nodes_added", []):
                    if isinstance(node, dict) and node.get("id"):
                        nodes_by_id[str(node["id"])] = dict(node)
                for dependency in payload.get("plan_dependencies_added", []):
                    if isinstance(dependency, dict) and dependency.get("id"):
                        plan["dependencies"].append(dict(dependency))
                for completed in payload.get("plan_nodes_completed", []):
                    if not isinstance(completed, dict):
                        continue
                    node = nodes_by_id.get(str(completed.get("node_id")))
                    if node:
                        node["status"] = "completed"
                        node["completed_at"] = event.created_at.isoformat()
                        node["verified_by_execution_id"] = event.source_execution_id
                        node["updated_at"] = event.created_at.isoformat()
                        node["version"] = int(node.get("version", 1)) + 1

        plan["nodes"] = list(nodes_by_id.values())[-_MAX_NODES:]
        plan["decisions"] = list(decisions_by_id.values())[-80:]
        plan["dependencies"] = plan["dependencies"][-300:]
        plan["updated_at"] = events[-1].created_at.isoformat() if events else _now().isoformat()
        state = dict(row.state_json or {})
        state["plan"] = plan
        row.state_json = state
        row.version += 1
        row.updated_at = _now()
        db.commit()
        try:
            from app.services.task_memory import _write_projection
            _write_projection(db, row)
        except Exception:
            logger.exception("Could not refresh task projection after plan-history rebuild")
        return {
            "rebuilt": True,
            "events_replayed": len(events),
            "nodes": len(plan["nodes"]),
            "decisions": len(plan["decisions"]),
            "constraints": len(plan["constraints"]),
            "dependencies": len(plan["dependencies"]),
        }


def compile_plan_context(task_state_id: str | None) -> str:
    """Compile the current hierarchy into a bounded working-context block."""
    if not task_state_id:
        return ""
    try:
        with SessionLocal() as db:
            row = db.get(models.TaskState, task_state_id)
            if row is None:
                return ""
            plan = dict((row.state_json or {}).get("plan") or {})
            root_objective = row.original_objective
    except Exception:
        logger.exception("Could not load hierarchical plan context")
        return ""
    nodes = [n for n in (plan.get("nodes") or []) if isinstance(n, dict)]
    if not nodes and not plan.get("root_summary") and not plan.get("decisions") and not plan.get("constraints") and not plan.get("dependencies"):
        return ""
    node_by_id = {
        str(node.get("id")): node for node in nodes if node.get("id")
    }
    selected_ids: set[str] = set()

    def include_ancestors(node: dict[str, Any]) -> None:
        current: dict[str, Any] | None = node
        depth = 0
        while current is not None and depth <= _MAX_NODES:
            node_id = str(current.get("id") or "")
            if not node_id or node_id in selected_ids:
                break
            selected_ids.add(node_id)
            parent_id = str(current.get("parent_id") or task_state_id)
            current = node_by_id.get(parent_id) if parent_id != task_state_id else None
            depth += 1

    for node in nodes:
        if node.get("status") in {"active", "blocked", "paused"}:
            include_ancestors(node)
    recent_nodes = sorted(
        nodes,
        key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""),
        reverse=True,
    )
    for node in recent_nodes[:16]:
        include_ancestors(node)
    for node in [item for item in recent_nodes if item.get("status") == "completed"][:6]:
        include_ancestors(node)
    if not selected_ids:
        for node in nodes[-20:]:
            include_ancestors(node)

    selected_nodes = [node for node in nodes if str(node.get("id") or "") in selected_ids]
    by_parent: dict[str, list[dict[str, Any]]] = {}
    for node in selected_nodes:
        by_parent.setdefault(str(node.get("parent_id") or task_state_id), []).append(node)
    status_priority = {"active": 0, "blocked": 1, "paused": 2, "proposed": 3, "completed": 4, "superseded": 5}
    for children in by_parent.values():
        children.sort(
            key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""),
            reverse=True,
        )
        children.sort(key=lambda item: status_priority.get(str(item.get("status")), 6))
    lines = ["[AgentForge evolving project plan]", "Root objective is immutable; user decisions outrank agent proposals."]
    if plan.get("root_summary"):
        lines.append("Root objective summary: " + _normal_text(plan.get("root_summary"), 1800))
    elif root_objective:
        lines.append("Root objective excerpt: " + _normal_text(root_objective, 1800))

    def walk(parent: str, depth: int, seen: set[str]) -> None:
        if depth > _MAX_NODES:
            return
        for node in by_parent.get(parent, []):
            node_id = str(node.get("id") or "")
            if not node_id or node_id in seen:
                continue
            seen.add(node_id)
            prefix = "  " * depth
            lines.append(
                f"{prefix}- [{node.get('status', 'proposed')}] {node.get('type', 'task')}: "
                f"{_normal_text(node.get('title'), 120)} (id={node_id}; source={node.get('source', 'agent')})"
                + (f" — {_normal_text(node.get('objective'), 220)}" if node.get("objective") else "")
            )
            walk(node_id, depth + 1, seen)
    walk(task_state_id, 0, set())
    node_titles = {
        str(node.get("id")): _normal_text(node.get("title"), 120)
        for node in nodes
    }
    dependencies = [
        edge for edge in (plan.get("dependencies") or [])
        if isinstance(edge, dict)
        and (str(edge.get("node_id")) in selected_ids or str(edge.get("depends_on_id")) in selected_ids)
    ]
    if dependencies:
        lines.append("Dependencies (a node depends on its prerequisite):")
        for edge in dependencies[-20:]:
            dependent = node_titles.get(str(edge.get("node_id")), "unknown task")
            prerequisite = node_titles.get(str(edge.get("depends_on_id")), "unknown task")
            reason = _normal_text(edge.get("reason"), 160)
            lines.append(f"- {dependent} depends on {prerequisite}" + (f": {reason}" if reason else ""))
    accepted = [d for d in (plan.get("decisions") or []) if isinstance(d, dict) and d.get("status") == "accepted"]
    proposed = [d for d in (plan.get("decisions") or []) if isinstance(d, dict) and d.get("status") == "proposed"]
    if accepted:
        lines.append("Accepted user decisions:")
        lines.extend(f"- {_normal_text(d.get('text'), 240)}" for d in accepted[-12:])
    if proposed:
        lines.append("Unaccepted agent/user proposals (not binding):")
        lines.extend(f"- {_normal_text(d.get('text'), 200)}" for d in proposed[-6:])
    constraints = plan.get("constraints") or []
    if constraints:
        lines.append("Explicit user constraints:")
        lines.extend(f"- {_normal_text(c.get('text'), 220)}" for c in constraints[-12:] if isinstance(c, dict))
    rendered = "\n".join(lines)
    return rendered[:_MAX_CONTEXT_CHARS]
