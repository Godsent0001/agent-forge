from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.deps import get_db
from app.graph import GraphValidationError, validate_new_link

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("", response_model=schemas.AgentOut)
def create_agent(payload: schemas.AgentCreate, db: Session = Depends(get_db)):
    agent = models.Agent(**payload.model_dump())
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@router.get("", response_model=list[schemas.AgentOut])
def list_agents(project_id: str, db: Session = Depends(get_db)):
    return db.query(models.Agent).filter(models.Agent.project_id == project_id).all()


@router.get("/{agent_id}", response_model=schemas.AgentOut)
def get_agent(agent_id: str, db: Session = Depends(get_db)):
    agent = db.get(models.Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.patch("/{agent_id}", response_model=schemas.AgentOut)
def update_agent(agent_id: str, payload: schemas.AgentUpdate, db: Session = Depends(get_db)):
    agent = db.get(models.Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(agent, field, value)
    db.commit()
    db.refresh(agent)
    return agent


@router.delete("/{agent_id}")
def delete_agent(agent_id: str, db: Session = Depends(get_db)):
    agent = db.get(models.Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    db.delete(agent)
    db.commit()
    return {"deleted": agent_id}


@router.post("/attach-tool")
def attach_tool(payload: schemas.AttachToolRequest, db: Session = Depends(get_db)):
    link = models.AgentToolLink(agent_id=payload.agent_id, tool_id=payload.tool_id)
    db.add(link)
    db.commit()
    return {"attached": True, "link_id": link.id}


@router.post("/attach-child-agent")
def attach_child_agent(payload: schemas.AttachChildAgentRequest, db: Session = Depends(get_db)):
    try:
        validate_new_link(db, payload.parent_agent_id, payload.child_agent_id)
    except GraphValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    link = models.AgentAgentLink(
        parent_agent_id=payload.parent_agent_id,
        child_agent_id=payload.child_agent_id,
        description=payload.description,
    )
    db.add(link)
    db.commit()
    return {"attached": True, "link_id": link.id}
