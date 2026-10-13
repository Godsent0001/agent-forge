"""Agent memory and lesson management routes for the v2 Runner."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app import models
from app.deps import get_db

router = APIRouter(prefix="/v2/agents", tags=["memory"])


class MemoryOut(BaseModel):
    id: str
    agent_id: str
    text: str
    kind: Literal["fact", "preference", "decision"]
    source_type: Literal["user_stated", "user_edited", "inferred"]
    source_execution_id: str | None
    created_at: datetime
    last_used_at: datetime | None
    use_count: int
    pinned: bool
    status: Literal["active", "superseded", "archived"]
    expires_at: datetime | None


class MemoryCreate(BaseModel):
    text: str = Field(min_length=1, max_length=200)
    kind: Literal["fact", "preference", "decision"] = "fact"
    pinned: bool = False


class MemoryUpdate(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=200)
    kind: Literal["fact", "preference", "decision"] | None = None
    pinned: bool | None = None
    status: Literal["active", "superseded", "archived"] | None = None


class LessonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    agent_id: str
    text: str
    evidence_execution_id: str | None
    status: Literal["active", "archived"]
    score: float
    created_at: datetime


class LessonCreate(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    evidence_execution_id: str | None = None
    score: float = 0.0


class LessonUpdate(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=300)
    status: Literal["active", "archived"] | None = None
    score: float | None = Field(default=None, ge=0, le=1)


def _agent_or_404(db: Session, agent_id: str) -> models.Agent:
    agent = db.get(models.Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


def _memory_out(row: models.MemoryEntry) -> MemoryOut:
    safe_kind = row.kind if row.kind in {"fact", "preference", "decision"} else "fact"
    safe_source = row.source_type if row.source_type in {"user_stated", "user_edited", "inferred"} else "user_stated"
    safe_status = row.status if row.status in {"active", "superseded", "archived"} else "active"
    return MemoryOut(
        id=row.id,
        agent_id=row.agent_id,
        text=row.content[:200],
        kind=safe_kind,
        source_type=safe_source,
        source_execution_id=row.source_execution_id,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        use_count=row.use_count or 0,
        pinned=bool(row.pinned),
        status=safe_status,
        expires_at=row.expires_at,
    )


@router.get("/{agent_id}/memory", response_model=list[MemoryOut])
def list_memory(
    agent_id: str,
    status: Literal["active", "superseded", "archived"] | None = None,
    db: Session = Depends(get_db),
) -> list[MemoryOut]:
    _agent_or_404(db, agent_id)
    query = db.query(models.MemoryEntry).filter(models.MemoryEntry.agent_id == agent_id)
    if status is not None:
        query = query.filter(models.MemoryEntry.status == status)
    rows = query.order_by(models.MemoryEntry.pinned.desc(), models.MemoryEntry.created_at.desc()).all()
    return [_memory_out(row) for row in rows]


@router.post("/{agent_id}/memory", response_model=MemoryOut)
def create_memory(agent_id: str, payload: MemoryCreate, db: Session = Depends(get_db)) -> MemoryOut:
    _agent_or_404(db, agent_id)
    row = models.MemoryEntry(
        agent_id=agent_id,
        content=payload.text.strip(),
        kind=payload.kind,
        source_type="user_edited",
        evidence="",
        pinned=payload.pinned,
        status="active",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _memory_out(row)


@router.patch("/{agent_id}/memory/{memory_id}", response_model=MemoryOut)
def update_memory(
    agent_id: str,
    memory_id: str,
    payload: MemoryUpdate,
    db: Session = Depends(get_db),
) -> MemoryOut:
    _agent_or_404(db, agent_id)
    row = db.query(models.MemoryEntry).filter_by(id=memory_id, agent_id=agent_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Memory item not found")
    values = payload.model_dump(exclude_unset=True)
    for field, value in values.items():
        if value is not None:
            if field == "text":
                row.content = value.strip()
                row.source_type = "user_edited"
                row.evidence = ""
            else:
                setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return _memory_out(row)


@router.delete("/{agent_id}/memory/{memory_id}")
def delete_memory(agent_id: str, memory_id: str, db: Session = Depends(get_db)) -> dict[str, bool]:
    _agent_or_404(db, agent_id)
    row = db.query(models.MemoryEntry).filter_by(id=memory_id, agent_id=agent_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Memory item not found")
    db.delete(row)
    db.commit()
    return {"deleted": True}


@router.delete("/{agent_id}/memory")
def clear_memory(agent_id: str, db: Session = Depends(get_db)) -> dict[str, int]:
    _agent_or_404(db, agent_id)
    count = db.query(models.MemoryEntry).filter_by(agent_id=agent_id).delete(synchronize_session=False)
    db.commit()
    return {"deleted": count}


@router.get("/{agent_id}/lessons", response_model=list[LessonOut])
def list_lessons(
    agent_id: str,
    status: Literal["active", "archived"] | None = None,
    db: Session = Depends(get_db),
) -> list[models.LessonEntry]:
    _agent_or_404(db, agent_id)
    query = db.query(models.LessonEntry).filter(models.LessonEntry.agent_id == agent_id)
    if status is not None:
        query = query.filter(models.LessonEntry.status == status)
    return query.order_by(models.LessonEntry.score.desc(), models.LessonEntry.created_at.desc()).all()


@router.post("/{agent_id}/lessons", response_model=LessonOut)
def create_lesson(agent_id: str, payload: LessonCreate, db: Session = Depends(get_db)) -> models.LessonEntry:
    _agent_or_404(db, agent_id)
    if payload.evidence_execution_id:
        execution = db.get(models.Execution, payload.evidence_execution_id)
        if execution is None or execution.root_agent_id != agent_id:
            raise HTTPException(status_code=404, detail="Evidence run not found for this agent")
    row = models.LessonEntry(
        agent_id=agent_id,
        text=payload.text.strip(),
        evidence_execution_id=payload.evidence_execution_id,
        score=payload.score,
        status="active",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{agent_id}/lessons/{lesson_id}", response_model=LessonOut)
def update_lesson(
    agent_id: str,
    lesson_id: str,
    payload: LessonUpdate,
    db: Session = Depends(get_db),
) -> models.LessonEntry:
    _agent_or_404(db, agent_id)
    row = db.query(models.LessonEntry).filter_by(id=lesson_id, agent_id=agent_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(row, field, value.strip() if field == "text" else value)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{agent_id}/lessons/{lesson_id}")
def delete_lesson(agent_id: str, lesson_id: str, db: Session = Depends(get_db)) -> dict[str, bool]:
    _agent_or_404(db, agent_id)
    row = db.query(models.LessonEntry).filter_by(id=lesson_id, agent_id=agent_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    db.delete(row)
    db.commit()
    return {"deleted": True}
