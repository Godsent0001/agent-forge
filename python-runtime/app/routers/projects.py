from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.deps import get_db
from app.infra.attachment_storage import AttachmentStorageError, remove_attachment_blobs

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=schemas.ProjectOut)
def create_project(payload: schemas.ProjectCreate, db: Session = Depends(get_db)):
    project = models.Project(name=payload.name, parallel_execution=payload.parallel_execution)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=list[schemas.ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.query(models.Project).all()


@router.get("/{project_id}", response_model=schemas.ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.get(models.Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=schemas.ProjectOut)
def update_project(project_id: str, payload: schemas.ProjectUpdate, db: Session = Depends(get_db)):
    project = db.get(models.Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if payload.name is not None:
        project.name = payload.name
    if payload.parallel_execution is not None:
        project.parallel_execution = payload.parallel_execution
    if payload.settings is not None:
        project.settings = payload.settings
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db)):
    project = db.get(models.Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    attachments = db.query(models.ProjectAttachment).filter_by(project_id=project_id).all()
    try:
        for attachment in attachments:
            remove_attachment_blobs(attachment.storage_key)
    except AttachmentStorageError as exc:
        raise HTTPException(
            status_code=500,
            detail="Project attachments could not be safely removed; retry deletion",
        ) from exc
    db.delete(project)
    db.commit()
    return {"deleted": project_id}
