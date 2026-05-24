"""Knowledge API routes."""
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..auth.security import Principal, get_current_principal
from ..config import get_settings
from ..database import get_db
from ..knowledge.ingestion import (
    extract_text_from_file,
    object_to_text,
    replace_source_chunks,
    upsert_case_source,
    create_global_file_source,
)
from ..knowledge.retrieval import search_knowledge
from ..models import ExperimentCase, KnowledgeSource
from ..schemas import KnowledgeGovernanceUpdate, KnowledgeSearchRequest, KnowledgeSearchResponse, KnowledgeSourceResponse

router = APIRouter()
settings = get_settings()
GLOBAL_KNOWLEDGE_EXTENSIONS = {".pdf", ".txt", ".md", ".csv", ".tsv", ".json", ".log"}


@router.get("/sources", response_model=list[KnowledgeSourceResponse])
async def list_sources(case_id: int | None = None, db: Session = Depends(get_db)):
    """List indexed knowledge sources."""
    query = db.query(KnowledgeSource)
    if case_id is not None:
        query = query.filter(KnowledgeSource.case_id == case_id)
    return query.order_by(KnowledgeSource.created_at.desc()).all()


@router.post("/sources/upload", response_model=KnowledgeSourceResponse, status_code=status.HTTP_201_CREATED)
async def upload_global_source(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Upload a global lab knowledge file and index it for Agent/RAG use."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in GLOBAL_KNOWLEDGE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type. Allowed: {', '.join(sorted(GLOBAL_KNOWLEDGE_EXTENSIONS))}",
        )
    content = await file.read()
    if len(content) > settings.max_upload_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds max upload size ({settings.max_upload_size} bytes)",
        )

    upload_dir = os.path.abspath(os.path.join(settings.upload_dir, "global_knowledge"))
    os.makedirs(upload_dir, exist_ok=True)
    filepath = os.path.abspath(os.path.join(upload_dir, f"{uuid.uuid4()}{ext}"))
    if not filepath.startswith(upload_dir):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid upload path")
    with open(filepath, "wb") as handle:
        handle.write(content)

    source = create_global_file_source(
        db,
        title=os.path.basename(file.filename or "global knowledge"),
        filepath=filepath,
        content_type=file.content_type,
    )
    source.owner_id = principal.user_id
    db.commit()
    db.refresh(source)
    return source


@router.get("/sources/{source_id}", response_model=KnowledgeSourceResponse)
async def get_source(source_id: int, db: Session = Depends(get_db)):
    """Get one indexed knowledge source."""
    source = db.query(KnowledgeSource).filter(KnowledgeSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Knowledge source {source_id} does not exist")
    return source


@router.post("/sources/{source_id}/reindex", response_model=KnowledgeSourceResponse)
async def reindex_source(source_id: int, db: Session = Depends(get_db)):
    """Reindex a source after parser, embedding, or vector backend changes."""
    source = db.query(KnowledgeSource).filter(KnowledgeSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Knowledge source {source_id} does not exist")
    if source.source_type == "case" and source.case_id:
        source = upsert_case_source(db, source.case)
    elif source.attachment is not None:
        text = extract_text_from_file(source.attachment.filepath, source.attachment.file_type)
        source.content_hash = source.attachment.content_hash
        source.metadata_json = {**(source.metadata_json or {}), "file_type": source.attachment.file_type, "filepath": source.attachment.filepath}
        replace_source_chunks(db, source, text)
    elif source.generated_content is not None:
        text = object_to_text(source.generated_content.content)
        source.metadata_json = {**(source.metadata_json or {}), "content_type": source.generated_content.content_type}
        replace_source_chunks(db, source, text)
    elif source.source_type == "global_attachment":
        filepath = (source.metadata_json or {}).get("filepath")
        if not filepath or not os.path.isfile(filepath):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Original global knowledge file is not available for reindex")
        text = extract_text_from_file(filepath, (source.metadata_json or {}).get("file_type"))
        replace_source_chunks(db, source, text)
    db.commit()
    db.refresh(source)
    return source


@router.patch("/sources/{source_id}/governance", response_model=KnowledgeSourceResponse)
async def update_source_governance(
    source_id: int,
    payload: KnowledgeGovernanceUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Review, approve, deprecate, or archive an indexed knowledge source."""
    if principal.role not in {"admin", "reviewer"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin or reviewer role required")
    source = db.query(KnowledgeSource).filter(KnowledgeSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Knowledge source {source_id} does not exist")
    source.governance_status = payload.governance_status
    source.reviewed_by_id = payload.reviewer_id or principal.user_id
    source.reviewed_at = datetime.now(timezone.utc)
    metadata = dict(source.metadata_json or {})
    if payload.note:
        metadata["governance_note"] = payload.note
    source.metadata_json = metadata
    db.commit()
    db.refresh(source)
    return source


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(source_id: int, db: Session = Depends(get_db)):
    """Delete a global knowledge source and its indexed chunks."""
    source = db.query(KnowledgeSource).filter(KnowledgeSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Knowledge source {source_id} does not exist")
    if source.source_type != "global_attachment":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only global knowledge sources can be deleted from this endpoint")
    # Remove file from disk if it exists
    filepath = (source.metadata_json or {}).get("filepath")
    if filepath and os.path.isfile(filepath):
        try:
            os.remove(filepath)
        except OSError:
            pass
    db.delete(source)
    db.commit()


@router.post("/search", response_model=KnowledgeSearchResponse)
async def search(request: KnowledgeSearchRequest, db: Session = Depends(get_db)):
    """Search indexed knowledge and return citation-ready results."""
    if request.case_id is not None:
        case = db.query(ExperimentCase).filter(ExperimentCase.id == request.case_id).first()
        if not case:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Case {request.case_id} does not exist")
    run, results = search_knowledge(
        db,
        query=request.query,
        case_id=request.case_id,
        source_type=request.source_type,
        top_k=request.top_k,
        task_id=request.task_id,
    )
    db.commit()
    return KnowledgeSearchResponse(
        query=request.query,
        retrieval_run_id=run.id,
        confidence=run.confidence or "low",
        no_answer=bool(run.no_answer),
        max_score=round(run.max_score or 0.0, 4),
        message=(run.filters_json or {}).get("low_confidence_message"),
        results=results,
    )
