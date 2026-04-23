"""
附件API路由
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List
import os
import uuid
from ..database import get_db
from ..models import Attachment, ExperimentCase
from ..schemas import AttachmentResponse
from ..config import get_settings

router = APIRouter()
settings = get_settings()


@router.post("/cases/{case_id}/attachments", response_model=AttachmentResponse, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    case_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """上传附件"""
    # 检查案例是否存在
    case = db.query(ExperimentCase).filter(ExperimentCase.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"案例 {case_id} 不存在"
        )

    # 检查文件大小
    content = await file.read()
    if len(content) > settings.max_upload_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"文件大小超过限制 ({settings.max_upload_size} bytes)"
        )

    # 生成唯一文件名
    file_ext = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    filepath = os.path.join(settings.upload_dir, unique_filename)

    # 保存文件
    with open(filepath, "wb") as f:
        f.write(content)

    # 创建附件记录
    attachment = Attachment(
        case_id=case_id,
        filename=file.filename,
        filepath=filepath,
        file_type=file.content_type
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)

    return attachment


@router.get("/cases/{case_id}/attachments", response_model=List[AttachmentResponse])
async def list_attachments(
    case_id: int,
    db: Session = Depends(get_db)
):
    """获取案例的附件列表"""
    attachments = db.query(Attachment).filter(Attachment.case_id == case_id).all()
    return attachments


@router.get("/attachments/{attachment_id}")
async def download_attachment(
    attachment_id: int,
    db: Session = Depends(get_db)
):
    """下载附件"""
    attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"附件 {attachment_id} 不存在"
        )

    if not os.path.exists(attachment.filepath):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在"
        )

    return FileResponse(
        path=attachment.filepath,
        filename=attachment.filename,
        media_type=attachment.file_type
    )


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment(
    attachment_id: int,
    db: Session = Depends(get_db)
):
    """删除附件"""
    attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"附件 {attachment_id} 不存在"
        )

    # 删除文件
    if os.path.exists(attachment.filepath):
        os.remove(attachment.filepath)

    # 删除数据库记录
    db.delete(attachment)
    db.commit()
    return None
