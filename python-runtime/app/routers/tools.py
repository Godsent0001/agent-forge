from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.deps import get_db
from app.tools.registry import known_tool_kinds

router = APIRouter(prefix="/tools", tags=["tools"])


@router.post("", response_model=schemas.ToolOut)
def create_tool(payload: schemas.ToolCreate, db: Session = Depends(get_db)):
    if db.get(models.Project, payload.project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if payload.kind not in known_tool_kinds():
        # An unknown kind would only fail later, mid-run, when the agent tries to use it.
        raise HTTPException(status_code=422, detail=f"Unknown tool kind: {payload.kind}")
    tool = models.Tool(**payload.model_dump())
    db.add(tool)
    db.commit()
    db.refresh(tool)
    return tool


@router.get("", response_model=list[schemas.ToolOut])
def list_tools(project_id: str, db: Session = Depends(get_db)):
    return db.query(models.Tool).filter(models.Tool.project_id == project_id).all()


@router.delete("/{tool_id}")
def delete_tool(tool_id: str, db: Session = Depends(get_db)):
    raise HTTPException(status_code=403, detail="Tool deletion capability has been disabled")
