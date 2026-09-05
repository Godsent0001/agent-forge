"""
Graph validation. Runs BEFORE writing an AgentAgentLink to the DB, so a
cyclic or too-deep hierarchy can never be saved in the first place.

This is the edit-time counterpart to the runtime guards proven in the
Phase 0.5 spike (context.descend() there catches it during execution;
this catches it during graph editing, which is the better UX — reject
at save time with a clear error, don't let a user build something that
can only fail later at run time).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AgentAgentLink

MAX_AGENT_DEPTH = 8


class GraphValidationError(ValueError):
    pass


def _children_of(db: Session, agent_id: str) -> list[str]:
    links = db.query(AgentAgentLink).filter(AgentAgentLink.parent_agent_id == agent_id).all()
    return [link.child_agent_id for link in links]


def would_create_cycle(db: Session, parent_agent_id: str, child_agent_id: str) -> bool:
    """
    Proposed edge: parent -> child. This creates a cycle iff parent is
    reachable *from* child, i.e. child (or one of its descendants)
    already leads back to parent.
    """
    if parent_agent_id == child_agent_id:
        return True

    visited: set[str] = set()
    stack = [child_agent_id]
    while stack:
        current = stack.pop()
        if current == parent_agent_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        stack.extend(_children_of(db, current))
    return False


def depth_of(db: Session, agent_id: str, _seen: set[str] | None = None) -> int:
    """Longest path from `agent_id` down through its child-agent tools."""
    seen = _seen or set()
    if agent_id in seen:
        # Should be unreachable if would_create_cycle is enforced everywhere,
        # but fail loudly rather than infinite-loop if it's ever bypassed.
        raise GraphValidationError(f"Cycle encountered while computing depth at {agent_id}")
    seen = seen | {agent_id}

    children = _children_of(db, agent_id)
    if not children:
        return 1
    return 1 + max(depth_of(db, child, seen) for child in children)


def validate_new_link(db: Session, parent_agent_id: str, child_agent_id: str) -> None:
    if would_create_cycle(db, parent_agent_id, child_agent_id):
        raise GraphValidationError(
            f"Attaching {child_agent_id} to {parent_agent_id} would create a cycle."
        )

    prospective_depth = depth_of(db, child_agent_id) + 1
    if prospective_depth > MAX_AGENT_DEPTH:
        raise GraphValidationError(
            f"Attaching {child_agent_id} to {parent_agent_id} would exceed "
            f"max agent nesting depth ({MAX_AGENT_DEPTH})."
        )
