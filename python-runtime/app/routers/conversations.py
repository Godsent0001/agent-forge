"""Persistent conversations and per-message feedback (D-14)."""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session, selectinload

from app import models
from app.core.llm.adapter import complete as adapter_complete
from app.core.llm.model_names import litellm_model
from app.core.llm.types import LLMParams
from app.deps import get_db

router = APIRouter(prefix="/v2", tags=["conversations"])
logger = logging.getLogger(__name__)


class ConversationCreate(BaseModel):
    project_id: str
    agent_id: str
    title: str = Field(default="New conversation", min_length=1, max_length=160)


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    agent_id: str
    title: str
    created_at: datetime


class MessageCreate(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=100_000)
    execution_id: str | None = None


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    role: Literal["user", "assistant"]
    content: str
    execution_id: str | None
    # Terminal status of the referenced run, so reloaded chats can still mark failures.
    execution_status: str | None = None
    created_at: datetime
    feedback_value: Literal[-1, 1] | None = None
    feedback_note: str | None = None


class FeedbackUpdate(BaseModel):
    value: Literal[-1, 1]
    note: str | None = Field(default=None, max_length=2000)


class MessageEdit(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)




def _is_placeholder_title(title: str | None) -> bool:
    return bool(re.fullmatch(r"New conversation(?: \(\d+\))?", (title or "").strip(), re.IGNORECASE))


def _fallback_conversation_title(content: str) -> str:
    """Create a short readable fallback, never reuse the entire first message."""
    normalized = re.sub(r"\s+", " ", content).strip()
    words = normalized.split(" ")
    title = " ".join(words[:7]).strip(" .,:;!?-")
    if len(words) > 7:
        title += "…"
    return title[:60].strip() or "New conversation"


def _unique_conversation_title(db: Session, conversation: models.Conversation, candidate: str) -> str:
    """Keep titles unique within an agent's project, case-insensitively."""
    base = re.sub(r"\s+", " ", candidate).strip().strip('"')[:160] or "New conversation"
    query = db.query(models.Conversation.title).filter(
        models.Conversation.project_id == conversation.project_id,
        models.Conversation.agent_id == conversation.agent_id,
    )
    if conversation.id:
        query = query.filter(models.Conversation.id != conversation.id)
    existing = {str(row[0]).strip().casefold() for row in query.all()}
    if base.casefold() not in existing:
        return base
    for suffix_number in range(2, 10_000):
        suffix = f" ({suffix_number})"
        unique = base[: 160 - len(suffix)].rstrip() + suffix
        if unique.casefold() not in existing:
            return unique
    # A UUID fragment makes this path safe even in an unusually large collision set.
    return f"{base[:140].rstrip()} ({conversation.id[:8]})"


def _generate_conversation_title(
    db: Session, conversation: models.Conversation, first_message: str
) -> str:
    """Generate a concise title with the agent's configured model, then de-duplicate it."""
    candidate = _fallback_conversation_title(first_message)
    agent = db.get(models.Agent, conversation.agent_id)
    if agent and agent.model and agent.provider and agent.provider.casefold() != "fake":
        try:
            turn = asyncio.run(adapter_complete(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Create a clear, specific title for this conversation. "
                            "Return only the title, 3 to 7 words, at most 60 characters. "
                            "Capture the user's actual topic or intended outcome. "
                            "Do not copy the full message, add quotes, use a generic title, "
                            "or include a date or numbering."
                        ),
                    },
                    {"role": "user", "content": first_message[:6000]},
                ],
                params=LLMParams(timeout_s=12, temperature=0.1, max_tokens=40),
                model=litellm_model(agent.provider, agent.model),
                provider=agent.provider,
                max_retries=1,
            ))
            generated = (turn.text or "").strip().strip("\"'").strip()
            generated = re.sub(r"^(?:title|conversation title)\s*:\s*", "", generated, flags=re.IGNORECASE)
            generated = re.sub(r"\\s+", " ", generated).strip(" .,:;!?-")
            if generated and len(generated) <= 60 and len(generated.split()) <= 9:
                candidate = generated
        except Exception:
            logger.warning("Conversation title generation failed; using concise fallback", exc_info=True)
    return _unique_conversation_title(db, conversation, candidate)


def _message_out(message: models.ConversationMessage, execution_status: str | None = None) -> MessageOut:
    feedback = message.feedback
    return MessageOut(
        id=message.id,
        conversation_id=message.conversation_id,
        role=message.role,
        content=message.content,
        execution_id=message.execution_id,
        execution_status=execution_status,
        created_at=message.created_at,
        feedback_value=feedback.value if feedback else None,
        feedback_note=feedback.note if feedback else None,
    )


def _get_conversation(db: Session, conversation_id: str) -> models.Conversation:
    conversation = db.get(models.Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    project_id: str,
    agent_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[models.Conversation]:
    if db.get(models.Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    query = db.query(models.Conversation).filter(models.Conversation.project_id == project_id)
    if agent_id is not None:
        query = query.filter(models.Conversation.agent_id == agent_id)
    return query.order_by(models.Conversation.created_at.desc()).limit(limit).all()


@router.post("/conversations", response_model=ConversationOut)
def create_conversation(
    payload: ConversationCreate, db: Session = Depends(get_db)
) -> models.Conversation:
    project = db.get(models.Project, payload.project_id)
    agent = db.get(models.Agent, payload.agent_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if agent is None or agent.project_id != project.id:
        raise HTTPException(status_code=404, detail="Agent not found in project")
    conversation = models.Conversation(
        project_id=project.id,
        agent_id=agent.id,
        title=payload.title.strip() or "New conversation",
    )
    conversation.title = _unique_conversation_title(db, conversation, conversation.title)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, db: Session = Depends(get_db)) -> dict[str, bool]:
    conversation = _get_conversation(db, conversation_id)
    db.delete(conversation)
    db.commit()
    return {"deleted": True}


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(
    conversation_id: str, db: Session = Depends(get_db)
) -> list[MessageOut]:
    _get_conversation(db, conversation_id)
    messages = (
        db.query(models.ConversationMessage)
        .options(selectinload(models.ConversationMessage.feedback))
        .filter(models.ConversationMessage.conversation_id == conversation_id)
        .order_by(models.ConversationMessage.created_at, models.ConversationMessage.id)
        .all()
    )
    execution_ids = {m.execution_id for m in messages if m.execution_id}
    statuses = dict(
        db.query(models.Execution.id, models.Execution.status)
        .filter(models.Execution.id.in_(execution_ids))
        .all()
    ) if execution_ids else {}
    return [_message_out(message, statuses.get(message.execution_id)) for message in messages]


@router.post("/conversations/{conversation_id}/messages", response_model=MessageOut)
def append_message(
    conversation_id: str,
    payload: MessageCreate,
    db: Session = Depends(get_db),
) -> MessageOut:
    conversation = _get_conversation(db, conversation_id)
    if payload.execution_id:
        if payload.role != "assistant":
            raise HTTPException(status_code=422, detail="Only assistant messages may reference an execution")
        execution = db.get(models.Execution, payload.execution_id)
        if (
            execution is None
            or execution.project_id != conversation.project_id
            or execution.root_agent_id != conversation.agent_id
        ):
            raise HTTPException(status_code=404, detail="Execution not found for conversation agent")
    elif payload.role == "assistant":
        raise HTTPException(status_code=422, detail="Assistant messages must reference their execution")

    message = models.ConversationMessage(
        conversation_id=conversation.id,
        role=payload.role,
        content=payload.content,
        execution_id=payload.execution_id,
    )
    db.add(message)
    if payload.role == "user" and _is_placeholder_title(conversation.title):
        conversation.title = _generate_conversation_title(db, conversation, payload.content)
    db.commit()
    db.refresh(message)
    return _message_out(message, execution.status if payload.execution_id else None)


@router.patch("/messages/{message_id}", response_model=MessageOut)
def edit_user_message(
    message_id: str,
    payload: MessageEdit,
    db: Session = Depends(get_db),
) -> MessageOut:
    """Edit a user turn and remove later turns so a resend starts from this point."""
    message = db.get(models.ConversationMessage, message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    if message.role != "user":
        raise HTTPException(status_code=422, detail="Only user messages can be edited")

    conversation = _get_conversation(db, message.conversation_id)
    ordered = (
        db.query(models.ConversationMessage)
        .filter(models.ConversationMessage.conversation_id == conversation.id)
        .order_by(models.ConversationMessage.created_at, models.ConversationMessage.id)
        .all()
    )
    try:
        edited_index = next(index for index, item in enumerate(ordered) if item.id == message.id)
    except StopIteration as exc:
        raise HTTPException(status_code=404, detail="Message not found in conversation") from exc

    edited_content = payload.content.strip()
    if not edited_content:
        raise HTTPException(status_code=422, detail="Message content cannot be empty")
    for later_message in ordered[edited_index + 1:]:
        db.delete(later_message)
    message.content = edited_content

    first_user = next((item for item in ordered if item.role == "user"), None)
    if first_user and first_user.id == message.id:
        conversation.title = _generate_conversation_title(db, conversation, message.content)
    db.commit()
    db.refresh(message)
    return _message_out(message)


@router.put("/messages/{message_id}/feedback")
def update_message_feedback(
    message_id: str,
    payload: FeedbackUpdate,
    db: Session = Depends(get_db),
) -> dict[str, bool | int]:
    message = db.get(models.ConversationMessage, message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    if message.role != "assistant":
        raise HTTPException(status_code=422, detail="Feedback is only supported for assistant messages")
    feedback = db.get(models.MessageFeedback, message_id)
    if feedback is None:
        feedback = models.MessageFeedback(message_id=message_id, value=payload.value, note=payload.note)
        db.add(feedback)
    else:
        feedback.value = payload.value
        feedback.note = payload.note
        feedback.created_at = datetime.now(feedback.created_at.tzinfo)
    db.commit()
    return {"ok": True, "value": payload.value}
