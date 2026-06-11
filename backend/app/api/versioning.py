"""Prompt and workflow version management API."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth.security import Principal, get_current_principal
from ..database import get_db
from ..models import PromptVersion, WorkflowVersion
from ..observability.audit import record_audit
from ..schemas import PromptVersionCreate, PromptVersionResponse, WorkflowVersionCreate, WorkflowVersionResponse

router = APIRouter()


def _require_reviewer(principal: Principal) -> None:
    if principal.role not in {"admin", "reviewer"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin or reviewer role required")


def _activate_only(db: Session, model, item) -> None:
    db.query(model).filter(model.name == item.name).update({"is_active": False})
    item.is_active = True


@router.post("/prompts", response_model=PromptVersionResponse, status_code=status.HTTP_201_CREATED)
async def create_prompt_version(
    payload: PromptVersionCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _require_reviewer(principal)
    data = payload.model_dump()
    data["created_by_id"] = data.get("created_by_id") or principal.user_id
    item = PromptVersion(**data)
    db.add(item)
    db.flush()
    if item.is_active:
        _activate_only(db, PromptVersion, item)
    record_audit(db, action="prompt_version.create", resource_type="prompt_version", resource_id=str(item.id))
    db.commit()
    db.refresh(item)
    return item


@router.get("/prompts", response_model=list[PromptVersionResponse])
async def list_prompt_versions(
    name: str | None = None,
    active: bool | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _ = principal
    query = db.query(PromptVersion)
    if name:
        query = query.filter(PromptVersion.name == name)
    if active is not None:
        query = query.filter(PromptVersion.is_active == active)
    return query.order_by(PromptVersion.created_at.desc()).all()


@router.post("/prompts/{prompt_id}/activate", response_model=PromptVersionResponse)
async def activate_prompt_version(
    prompt_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _require_reviewer(principal)
    item = db.query(PromptVersion).filter(PromptVersion.id == prompt_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Prompt version {prompt_id} does not exist")
    _activate_only(db, PromptVersion, item)
    record_audit(db, action="prompt_version.activate", resource_type="prompt_version", resource_id=str(item.id))
    db.commit()
    db.refresh(item)
    return item


@router.post("/workflows", response_model=WorkflowVersionResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow_version(
    payload: WorkflowVersionCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _require_reviewer(principal)
    data = payload.model_dump()
    data["created_by_id"] = data.get("created_by_id") or principal.user_id
    item = WorkflowVersion(**data)
    db.add(item)
    db.flush()
    if item.is_active:
        _activate_only(db, WorkflowVersion, item)
    record_audit(db, action="workflow_version.create", resource_type="workflow_version", resource_id=str(item.id))
    db.commit()
    db.refresh(item)
    return item


@router.get("/workflows", response_model=list[WorkflowVersionResponse])
async def list_workflow_versions(
    name: str | None = None,
    active: bool | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _ = principal
    query = db.query(WorkflowVersion)
    if name:
        query = query.filter(WorkflowVersion.name == name)
    if active is not None:
        query = query.filter(WorkflowVersion.is_active == active)
    return query.order_by(WorkflowVersion.created_at.desc()).all()


@router.post("/workflows/{workflow_id}/activate", response_model=WorkflowVersionResponse)
async def activate_workflow_version(
    workflow_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _require_reviewer(principal)
    item = db.query(WorkflowVersion).filter(WorkflowVersion.id == workflow_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Workflow version {workflow_id} does not exist")
    _activate_only(db, WorkflowVersion, item)
    record_audit(db, action="workflow_version.activate", resource_type="workflow_version", resource_id=str(item.id))
    db.commit()
    db.refresh(item)
    return item
