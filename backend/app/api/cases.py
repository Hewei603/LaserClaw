"""Experiment case API routes."""
from __future__ import annotations

import json
import os
import zipfile
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..auth.acl import accessible_case_ids, assert_case_delete, assert_case_edit, assert_case_view, has_project_role, is_admin
from ..auth.security import Principal, get_current_principal
from ..database import get_db
from ..knowledge.ingestion import upsert_case_source
from ..models import Attachment, CaseComponentItem, CaseModule, ExperimentCase, GeneratedContent, KnowledgeSource, Project
from ..observability.audit import record_audit
from ..schemas import ExperimentCaseCreate, ExperimentCaseResponse, ExperimentCaseUpdate

router = APIRouter()


def get_case_or_404(case_id: int, db: Session) -> ExperimentCase:
    case = db.query(ExperimentCase).filter(ExperimentCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Case {case_id} does not exist")
    return case


@router.post("", response_model=ExperimentCaseResponse, status_code=status.HTTP_201_CREATED)
async def create_case(
    case_data: ExperimentCaseCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Create an experiment case and index it for retrieval."""
    payload = case_data.model_dump()
    if payload.get("project_id") is not None:
        project = db.query(Project).filter(Project.id == payload["project_id"]).first()
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {payload['project_id']} does not exist")
        if (
            principal.user_id is not None
            and not is_admin(principal)
            and project.visibility != "organization"
            and not has_project_role(db, project.id, principal, "editor")
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Project editor role required")
    if payload.get("owner_id") is None and principal.user_id is not None:
        payload["owner_id"] = principal.user_id
    case = ExperimentCase(**payload)
    db.add(case)
    db.flush()
    upsert_case_source(db, case)
    record_audit(db, action="case.create", resource_type="case", resource_id=str(case.id))
    db.commit()
    db.refresh(case)
    return case


@router.get("", response_model=list[ExperimentCaseResponse])
async def list_cases(
    skip: int = 0,
    limit: int = 100,
    project_id: int | None = None,
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """List experiment cases."""
    query = db.query(ExperimentCase)
    visible_ids = accessible_case_ids(db, principal)
    if visible_ids is not None:
        if not visible_ids:
            return []
        query = query.filter(ExperimentCase.id.in_(visible_ids))
    if project_id is not None:
        query = query.filter(ExperimentCase.project_id == project_id)
    if status_filter:
        query = query.filter(ExperimentCase.status == status_filter)
    return query.offset(skip).limit(limit).all()


@router.get("/{case_id}", response_model=ExperimentCaseResponse)
async def get_case(case_id: int, db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    """Get one experiment case."""
    case = get_case_or_404(case_id, db)
    assert_case_view(db, case, principal)
    return case


@router.put("/{case_id}", response_model=ExperimentCaseResponse)
async def update_case(
    case_id: int,
    case_data: ExperimentCaseUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Update an experiment case and refresh the knowledge index."""
    case = get_case_or_404(case_id, db)
    assert_case_edit(db, case, principal)
    payload = case_data.model_dump(exclude_unset=True)
    if payload.get("project_id") is not None:
        project = db.query(Project).filter(Project.id == payload["project_id"]).first()
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {payload['project_id']} does not exist")
        if (
            principal.user_id is not None
            and not is_admin(principal)
            and project.visibility != "organization"
            and not has_project_role(db, project.id, principal, "editor")
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Project editor role required")
    for field, value in payload.items():
        setattr(case, field, value)
    upsert_case_source(db, case)
    record_audit(db, action="case.update", resource_type="case", resource_id=str(case.id))
    db.commit()
    db.refresh(case)
    return case


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_case(case_id: int, db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    """Delete an experiment case."""
    case = get_case_or_404(case_id, db)
    assert_case_delete(db, case, principal)
    record_audit(db, action="case.delete", resource_type="case", resource_id=str(case.id))
    db.delete(case)
    db.commit()
    return None


def _json_default(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


@router.get("/{case_id}/bundle")
async def export_case_bundle(
    case_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Export a complete case bundle as a zip archive."""
    case = get_case_or_404(case_id, db)
    assert_case_view(db, case, principal)
    attachments = db.query(Attachment).filter(Attachment.case_id == case_id).all()
    generated = db.query(GeneratedContent).filter(GeneratedContent.case_id == case_id).all()
    sources = db.query(KnowledgeSource).filter(KnowledgeSource.case_id == case_id).all()
    modules = db.query(CaseModule).filter(CaseModule.case_id == case_id).all()
    component_items = db.query(CaseComponentItem).filter(CaseComponentItem.case_id == case_id).all()
    manifest = {
        "case": {
            "id": case.id,
            "project_id": case.project_id,
            "title": case.title,
            "description": case.description,
            "cavity_type": case.cavity_type,
            "goal": case.goal,
            "status": case.status,
            "visibility": case.visibility,
            "schema_version": case.schema_version,
            "tags": case.tags or [],
            "parameters": case.parameters or {},
            "symptoms": case.symptoms or [],
            "measurements": case.measurements or {},
            "safety_notes": case.safety_notes,
            "conclusions": case.conclusions,
            "owner_id": case.owner_id,
            "created_at": case.created_at,
            "updated_at": case.updated_at,
        },
        "attachments": [
            {
                "id": item.id,
                "filename": item.filename,
                "file_type": item.file_type,
                "content_hash": item.content_hash,
                "uploaded_at": item.uploaded_at,
            }
            for item in attachments
        ],
        "generated_contents": [
            {
                "id": item.id,
                "content_type": item.content_type,
                "content": item.content,
                "model": item.model,
                "prompt_version": item.prompt_version,
                "generated_at": item.generated_at,
            }
            for item in generated
        ],
        "knowledge_sources": [
            {
                "id": item.id,
                "source_type": item.source_type,
                "title": item.title,
                "uri": item.uri,
                "content_hash": item.content_hash,
                "governance_status": item.governance_status,
                "version": item.version,
                "metadata_json": item.metadata_json or {},
            }
            for item in sources
        ],
        "case_modules": [
            {
                "id": item.id,
                "module_type": item.module_type,
                "title": item.title,
                "status": item.status,
                "config_json": item.config_json or {},
                "result_json": item.result_json or {},
                "files": [
                    {
                        "id": file.id,
                        "filename": file.filename,
                        "file_type": file.file_type,
                        "file_role": file.file_role,
                        "content_hash": file.content_hash,
                        "metadata_json": file.metadata_json or {},
                        "created_at": file.created_at,
                    }
                    for file in item.files
                ],
            }
            for item in modules
        ],
        "component_items": [
            {
                "id": item.id,
                "module_id": item.module_id,
                "category": item.category,
                "name": item.name,
                "specification": item.specification,
                "quantity": item.quantity,
                "unit": item.unit,
                "purpose": item.purpose,
                "required": item.required,
                "owned": item.owned,
                "procurement_status": item.procurement_status,
                "vendor": item.vendor,
                "part_number": item.part_number,
                "notes": item.notes,
                "source": item.source,
            }
            for item in component_items
        ],
    }

    tmp = NamedTemporaryFile(prefix=f"laserclaw-case-{case_id}-", suffix=".zip", delete=False)
    tmp.close()
    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2, default=_json_default))
        for item in generated:
            bundle.writestr(f"generated/{item.content_type}-{item.id}.json", json.dumps(item.content, ensure_ascii=False, indent=2))
        for attachment in attachments:
            if attachment.filepath and os.path.isfile(attachment.filepath):
                bundle.write(attachment.filepath, arcname=f"attachments/{attachment.filename}")
        for module in modules:
            for item in module.files:
                if item.filepath and os.path.isfile(item.filepath):
                    bundle.write(item.filepath, arcname=f"modules/{module.id}/{item.file_role}/{item.filename}")
    record_audit(db, action="case.bundle.export", resource_type="case", resource_id=str(case.id))
    db.commit()
    return FileResponse(tmp.name, filename=f"laserclaw-case-{case_id}-bundle.zip", media_type="application/zip")
