"""Attachment API routes."""
from __future__ import annotations

import hashlib
import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..knowledge.ingestion import create_attachment_source
from ..knowledge.ingestion import create_generated_content_source
from ..models import Attachment, ExperimentCase, GeneratedContent
from ..observability.audit import record_audit
from ..providers import get_ai_provider
from ..schemas import AttachmentResponse

router = APIRouter()
settings = get_settings()

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
TEXT_EXTENSIONS = {".pdf", ".txt", ".md", ".csv", ".json", ".log"}
ALLOWED_EXTENSIONS = TEXT_EXTENSIONS | IMAGE_EXTENSIONS


def _safe_upload_path(filename: str) -> tuple[str, str]:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    unique_filename = f"{uuid.uuid4()}{ext}"
    filepath = os.path.abspath(os.path.join(settings.upload_dir, unique_filename))
    upload_root = os.path.abspath(settings.upload_dir)
    if not filepath.startswith(upload_root):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid upload path")
    return unique_filename, filepath


@router.post("/cases/{case_id}/attachments", response_model=AttachmentResponse, status_code=status.HTTP_201_CREATED)
async def upload_attachment(case_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload an attachment and index extracted text into the knowledge base."""
    case = db.query(ExperimentCase).filter(ExperimentCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Case {case_id} does not exist")

    _, filepath = _safe_upload_path(file.filename or "")
    content = await file.read()
    if len(content) > settings.max_upload_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds max upload size ({settings.max_upload_size} bytes)",
        )

    os.makedirs(settings.upload_dir, exist_ok=True)
    with open(filepath, "wb") as handle:
        handle.write(content)

    attachment = Attachment(
        case_id=case_id,
        filename=os.path.basename(file.filename or "attachment"),
        filepath=filepath,
        file_type=file.content_type,
        content_hash=hashlib.sha256(content).hexdigest(),
    )
    db.add(attachment)
    db.flush()
    if ext := os.path.splitext(attachment.filename)[1].lower():
        if ext not in IMAGE_EXTENSIONS:
            create_attachment_source(db, attachment)
    record_audit(db, action="attachment.upload", resource_type="attachment", resource_id=str(attachment.id))
    db.commit()
    db.refresh(attachment)
    return attachment


@router.post("/attachments/{attachment_id}/analyze", response_model=dict)
async def analyze_attachment_image(attachment_id: int, db: Session = Depends(get_db)):
    """Analyze an uploaded case image and save the result as generated content."""
    attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Attachment {attachment_id} does not exist")
    ext = os.path.splitext(attachment.filename)[1].lower()
    if ext not in IMAGE_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Only image attachments can be analyzed")
    if not os.path.exists(attachment.filepath):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment file is missing")

    with open(attachment.filepath, "rb") as handle:
        image_data = handle.read()
    case = db.query(ExperimentCase).filter(ExperimentCase.id == attachment.case_id).first()
    context = {
        "filename": attachment.filename,
        "mime_type": attachment.file_type,
        "case": {
            "id": case.id,
            "title": case.title,
            "description": case.description,
            "cavity_type": case.cavity_type,
            "goal": case.goal,
            "parameters": case.parameters or {},
            "symptoms": case.symptoms or [],
        } if case else None,
    }
    content = await get_ai_provider().analyze_image(image_data, attachment.file_type or "image/png", context)
    content["attachment_id"] = attachment.id
    generated = GeneratedContent(
        case_id=attachment.case_id,
        content_type="image_analysis",
        content=content,
        prompt_version="image_analysis_v1",
    )
    db.add(generated)
    db.flush()
    create_generated_content_source(db, generated)
    record_audit(db, action="attachment.analyze_image", resource_type="attachment", resource_id=str(attachment.id))
    db.commit()
    db.refresh(generated)
    return {"generated_content_id": generated.id, "content": generated.content}


@router.get("/cases/{case_id}/attachments", response_model=list[AttachmentResponse])
async def list_attachments(case_id: int, db: Session = Depends(get_db)):
    """List attachments for a case."""
    return db.query(Attachment).filter(Attachment.case_id == case_id).all()


@router.get("/attachments/{attachment_id}")
async def download_attachment(attachment_id: int, db: Session = Depends(get_db)):
    """Download an attachment."""
    attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Attachment {attachment_id} does not exist")
    if not os.path.exists(attachment.filepath):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment file is missing")
    record_audit(db, action="attachment.download", resource_type="attachment", resource_id=str(attachment.id))
    db.commit()
    return FileResponse(path=attachment.filepath, filename=attachment.filename, media_type=attachment.file_type)


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment(attachment_id: int, db: Session = Depends(get_db)):
    """Delete an attachment and its indexed knowledge."""
    attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Attachment {attachment_id} does not exist")
    if os.path.exists(attachment.filepath):
        os.remove(attachment.filepath)
    record_audit(db, action="attachment.delete", resource_type="attachment", resource_id=str(attachment.id))
    db.delete(attachment)
    db.commit()
    return None
