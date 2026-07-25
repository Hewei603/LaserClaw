"""Structured optics inventory API (L0 storage + L1 evaluation)."""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from ..auth.acl import can_manage_knowledge
from ..auth.security import Principal, get_current_principal
from ..config import get_settings
from ..database import get_db
from ..inventory.evaluator import evaluate_candidates
from ..inventory.importer import import_workbook
from ..models import CoatingSpec, InventoryItem
from ..observability.audit import record_audit
from ..schemas import (
    ComponentMatchRequest,
    InventoryImportResponse,
    InventoryItemResponse,
)

router = APIRouter()
settings = get_settings()


@router.post("/import", response_model=InventoryImportResponse)
async def import_inventory(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Import a lab inventory workbook (xlsx).  Reviewer/admin only.

    Re-importing the same source file replaces its previous rows (idempotent
    refresh), keeping other sources untouched.
    """
    if not can_manage_knowledge(principal):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin or reviewer role required")
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only .xlsx workbooks are supported")

    content = await file.read()
    if len(content) > settings.max_upload_size:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds max upload size ({settings.max_upload_size} bytes)",
        )

    upload_dir = Path(settings.upload_dir) / "inventory"
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored = upload_dir / f"{uuid.uuid4().hex}.xlsx"
    stored.write_bytes(content)

    source_name = os.path.basename(file.filename or "inventory.xlsx")
    try:
        db.query(InventoryItem).filter(InventoryItem.source_file == source_name).delete()
        report = import_workbook(db, stored, source_file=source_name)
    except RuntimeError as exc:
        stored.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc))
    except Exception as exc:
        db.rollback()
        stored.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Import failed: {exc}")

    record_audit(
        db,
        action="inventory.import",
        resource_type="inventory",
        resource_id=source_name,
        actor=principal.actor,
        user_id=principal.user_id,
        metadata=report.as_dict() | {"stored_path": str(stored)},
    )
    db.commit()
    return InventoryImportResponse(source_file=source_name, **report.as_dict())


@router.get("/items", response_model=list[InventoryItemResponse])
async def list_items(
    category: str | None = None,
    wavelength_nm: float | None = None,
    function: str | None = None,
    needs_review: bool = False,
    limit: int = 100,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """List/filter inventory items.  Wavelength+function filters use the typed
    coating rows (SQL-level, not text search)."""
    _ = principal
    query = db.query(InventoryItem).options(selectinload(InventoryItem.coatings))
    if category:
        query = query.filter(InventoryItem.category == category)
    if needs_review:
        query = query.filter(InventoryItem.parse_confidence != "parsed")
    if wavelength_nm is not None or function:
        query = query.join(CoatingSpec)
        if wavelength_nm is not None:
            query = query.filter(CoatingSpec.wl_min_nm - 8 <= wavelength_nm,
                                 CoatingSpec.wl_max_nm + 8 >= wavelength_nm)
        if function:
            fn = function.upper()
            if fn in ("AR", "HT"):
                query = query.filter(or_(CoatingSpec.function == "AR", CoatingSpec.function == "HT"))
            else:
                query = query.filter(CoatingSpec.function == fn)
    return query.distinct().limit(min(limit, 500)).all()


@router.post("/match")
async def match_components(
    payload: ComponentMatchRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """L1 evaluation: requirement spec -> structured verdicts + dominance frontier."""
    _ = principal
    result = evaluate_candidates(db, payload.model_dump(exclude_none=True))
    return result
