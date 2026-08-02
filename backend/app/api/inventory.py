"""Structured optics inventory API (L0 storage + L1 evaluation)."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from ..auth.acl import can_manage_knowledge
from ..auth.security import Principal, get_current_principal
from ..config import get_settings
from ..database import get_db
from ..inventory.evaluator import evaluate_candidates
from ..inventory.importer import import_workbook
from ..models import CoatingSpec, InventoryItem, InventoryLoan
from ..observability.audit import record_audit
from ..schemas import (
    ComponentMatchRequest,
    InventoryBorrowRequest,
    InventoryConditionRequest,
    InventoryImportResponse,
    InventoryItemResponse,
    InventoryReturnRequest,
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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要 reviewer 或 admin 权限")
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="仅支持 .xlsx 工作簿(请用 Excel 另存为 .xlsx)")

    content = await file.read()
    if len(content) > settings.max_upload_size:
        raise HTTPException(
            status_code=413,
            detail=f"文件超过大小上限({settings.max_upload_size // (1024 * 1024)} MB)",
        )

    upload_dir = Path(settings.upload_dir) / "inventory"
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored = upload_dir / f"{uuid.uuid4().hex}.xlsx"
    stored.write_bytes(content)

    source_name = os.path.basename(file.filename or "inventory.xlsx")

    # Re-importing replaces this batch's rows, which retires their ids — and
    # SQLite reuses rowids, so an open loan would silently re-point at whatever
    # component happens to take the freed id. Refuse instead of corrupting.
    outstanding = (
        db.query(InventoryLoan)
        .join(InventoryItem, InventoryLoan.item_id == InventoryItem.id)
        .filter(InventoryItem.source_file == source_name, InventoryLoan.returned_at.is_(None))
        .count()
    )
    if outstanding:
        stored.unlink(missing_ok=True)
        # Deliberately the ONLY way out: returning the items. Deleting the
        # batch would cascade the open loans away — exactly the ledger this
        # guard exists to protect — so it must not be offered as an escape.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(f"该清单还有 {outstanding} 件元件借出未归还,重新导入会让借用记录对不上元件。"
                    f"请先在元件表里逐件点「归还」,再重新导入。"),
        )

    try:
        # Row-by-row so the CoatingSpec/InventoryLoan cascades actually run; a
        # bulk delete bypasses the ORM and orphans the child rows.
        for stale in db.query(InventoryItem).filter(InventoryItem.source_file == source_name).all():
            db.delete(stale)
        report = import_workbook(db, stored, source_file=source_name)
    except RuntimeError as exc:
        stored.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED,
                            detail=f"服务端缺少解析依赖:{exc}")
    except Exception as exc:
        db.rollback()
        stored.unlink(missing_ok=True)
        reason = str(exc)
        if "not a zip file" in reason.lower():
            # openpyxl's BadZipFile leaks "zip" jargon at someone who uploaded
            # what they believe is an Excel file — explain in their terms.
            reason = "文件不是有效的 xlsx 工作簿(可能是改了扩展名的文本/旧版 xls 文件,请用 Excel 另存为 .xlsx)"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"导入失败:{reason}")

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


@router.delete("/items")
async def clear_inventory(
    source_file: str | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Delete inventory rows — all of them, or one import batch by source file.

    Without this, a re-import under a slightly different filename ("镜片统计-
    修正版.xlsx") silently doubles the inventory and permanently pollutes every
    later component match, with no recovery path in the UI.
    """
    if not can_manage_knowledge(principal):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要 reviewer 或 admin 权限")
    # Same guard as re-import, for the same reason: deleting items cascades
    # their loans away, so a batch with something still in someone's drawer
    # would silently erase "who has it" and the item would list as available
    # again after the next import. Return first, then delete.
    open_loans = db.query(InventoryLoan).join(InventoryItem, InventoryLoan.item_id == InventoryItem.id)
    if source_file:
        open_loans = open_loans.filter(InventoryItem.source_file == source_file)
    outstanding = open_loans.filter(InventoryLoan.returned_at.is_(None)).count()
    if outstanding:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(f"该批次还有 {outstanding} 件元件借出未归还,删除会连借用记录一起抹掉。"
                    f"请先在元件表里逐件点「归还」,再删除批次。"),
        )
    query = db.query(InventoryItem)
    if source_file:
        query = query.filter(InventoryItem.source_file == source_file)
    # ORM-level deletes so the CoatingSpec cascade ("all, delete-orphan") runs.
    items = query.all()
    for item in items:
        db.delete(item)
    record_audit(
        db,
        action="inventory.clear",
        resource_type="inventory",
        resource_id=source_file or "all",
        actor=principal.actor,
        user_id=principal.user_id,
        metadata={"deleted_items": len(items)},
    )
    db.commit()
    return {"deleted_items": len(items), "source_file": source_file}


@router.get("/sources")
async def list_sources(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Distinct import batches (source file + row count), for selective cleanup."""
    _ = principal
    from sqlalchemy import func

    rows = (
        db.query(InventoryItem.source_file, func.count(InventoryItem.id))
        .group_by(InventoryItem.source_file)
        .all()
    )
    return [{"source_file": name or "(未记录)", "items": count} for name, count in rows]


def _loan_payload(loan: InventoryLoan, item: InventoryItem | None) -> dict:
    return {
        "id": loan.id,
        "item_id": loan.item_id,
        "item_name": item.name if item else None,
        "borrower_name": loan.borrower_name,
        "quantity": loan.quantity,
        "purpose": loan.purpose,
        "borrowed_at": loan.borrowed_at,
        "expected_return_at": loan.expected_return_at,
        "returned_at": loan.returned_at,
        "returned_note": loan.returned_note,
        "is_open": loan.returned_at is None,
    }


def _open_loan_totals(db: Session, item_ids: list[int] | None = None) -> dict[int, float]:
    """How much of each item is signed out right now, keyed by item id."""
    query = (
        db.query(InventoryLoan.item_id, func.coalesce(func.sum(InventoryLoan.quantity), 0.0))
        .filter(InventoryLoan.returned_at.is_(None))
    )
    if item_ids is not None:
        query = query.filter(InventoryLoan.item_id.in_(item_ids))
    return {item_id: float(total) for item_id, total in query.group_by(InventoryLoan.item_id).all()}


@router.post("/items/{item_id}/borrow")
async def borrow_item(
    item_id: int,
    payload: InventoryBorrowRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Sign an item out. Anyone may borrow — reviewer rights are for curation."""
    # Lock the item row for the duration of the check-then-write, so two
    # concurrent borrows cannot both be told the last one is free. READ
    # COMMITTED alone does not give that: both transactions would pass the
    # availability check and both commit. On Postgres this emits FOR UPDATE;
    # SQLite ignores it, but its single-writer lock serialises anyway.
    item = (
        db.query(InventoryItem)
        .filter(InventoryItem.id == item_id)
        .with_for_update()
        .first()
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"元件 {item_id} 不存在")

    if item.effective_condition == "damaged":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="该元件已标记为损坏,不能借出。如需送修请先撤销损坏标记。")

    already_out = _open_loan_totals(db, [item_id]).get(item_id, 0.0)
    available = float(item.quantity or 0) - already_out
    if payload.quantity > available:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(f"可用数量不足:库存 {float(item.quantity or 0):g},已借出 {already_out:g},"
                    f"可借 {max(available, 0):g},本次申请 {payload.quantity:g}。"),
        )

    loan = InventoryLoan(
        item_id=item_id,
        borrower_name=payload.borrower_name.strip(),
        borrower_user_id=principal.user_id,
        quantity=payload.quantity,
        purpose=payload.purpose,
        expected_return_at=payload.expected_return_at,
    )
    db.add(loan)
    db.flush()
    record_audit(db, action="inventory.borrow", resource_type="inventory_loan",
                 resource_id=str(loan.id), actor=principal.actor, user_id=principal.user_id,
                 metadata={"item_id": item_id, "quantity": payload.quantity,
                           "borrower": loan.borrower_name})
    db.commit()
    db.refresh(loan)
    return _loan_payload(loan, item)


@router.post("/loans/{loan_id}/return")
async def return_loan(
    loan_id: int,
    payload: InventoryReturnRequest = InventoryReturnRequest(),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Return a borrowed item. The row is kept, not deleted — that is the history."""
    loan = db.query(InventoryLoan).filter(InventoryLoan.id == loan_id).first()
    if loan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"借用记录 {loan_id} 不存在")
    if loan.returned_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该借用记录已经归还过了。")

    loan.returned_at = datetime.now(timezone.utc)
    loan.returned_note = payload.note

    item = db.query(InventoryItem).filter(InventoryItem.id == loan.item_id).first()
    # Returning something broken is the moment a person actually knows it is
    # broken, so this is the natural place to record it.
    if payload.condition_on_return and item is not None:
        item.condition_manual = payload.condition_on_return
        item.condition_note = payload.note
        item.condition_marked_by = principal.actor
        item.condition_marked_at = datetime.now(timezone.utc)

    record_audit(db, action="inventory.return", resource_type="inventory_loan",
                 resource_id=str(loan.id), actor=principal.actor, user_id=principal.user_id,
                 metadata={"item_id": loan.item_id, "condition_on_return": payload.condition_on_return})
    db.commit()
    db.refresh(loan)
    return _loan_payload(loan, item)


@router.get("/loans")
async def list_loans(
    open_only: bool = True,
    item_id: int | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Loan records — by default only what is currently out."""
    _ = principal
    query = db.query(InventoryLoan).options(selectinload(InventoryLoan.item))
    if open_only:
        query = query.filter(InventoryLoan.returned_at.is_(None))
    if item_id is not None:
        query = query.filter(InventoryLoan.item_id == item_id)
    loans = query.order_by(InventoryLoan.borrowed_at.desc()).limit(500).all()
    return [_loan_payload(loan, loan.item) for loan in loans]


@router.patch("/items/{item_id}/condition")
async def set_item_condition(
    item_id: int,
    payload: InventoryConditionRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Mark an item damaged / uncertain / ok, or clear the human verdict.

    Written to ``condition_manual``, which the importer never touches, so a
    re-import of the workbook cannot resurrect a mirror somebody broke.
    Clearing it (``condition: null``) needs curation rights: undoing someone
    else's damage report should not be a one-click accident.
    """
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"元件 {item_id} 不存在")

    if payload.condition is None and not can_manage_knowledge(principal):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="撤销损坏标记需要 reviewer 或 admin 权限")

    item.condition_manual = payload.condition
    item.condition_note = payload.note
    item.condition_marked_by = principal.actor if payload.condition else None
    item.condition_marked_at = datetime.now(timezone.utc) if payload.condition else None

    record_audit(db, action="inventory.mark_condition", resource_type="inventory",
                 resource_id=str(item_id), actor=principal.actor, user_id=principal.user_id,
                 metadata={"condition": payload.condition, "note": payload.note})
    db.commit()
    db.refresh(item)
    return {"item_id": item.id, "condition": item.condition,
            "condition_manual": item.condition_manual,
            "effective_condition": item.effective_condition,
            "condition_note": item.condition_note,
            "condition_marked_by": item.condition_marked_by}


@router.get("/items", response_model=list[InventoryItemResponse])
async def list_items(
    category: str | None = None,
    wavelength_nm: float | None = None,
    function: str | None = None,
    needs_review: bool = False,
    condition: str | None = None,
    available_only: bool = False,
    limit: int = 100,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """List/filter inventory items.  Wavelength+function filters use the typed
    coating rows (SQL-level, not text search).

    Availability is computed per request from open loans rather than stored: the
    importer overwrites ``quantity`` on every re-import, so anything bookkept
    there would be silently reverted.
    """
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
    # Both filters run in SQL, BEFORE the limit. Filtering the limited page in
    # Python silently drops every match past row `limit` — with a real workbook
    # (hundreds of rows) a damaged mirror at row 501 would simply never appear.
    if condition:
        query = query.filter(
            func.coalesce(InventoryItem.condition_manual, InventoryItem.condition, "ok") == condition
        )
    open_loan_sums = (
        db.query(
            InventoryLoan.item_id.label("loan_item_id"),
            func.coalesce(func.sum(InventoryLoan.quantity), 0.0).label("loaned"),
        )
        .filter(InventoryLoan.returned_at.is_(None))
        .group_by(InventoryLoan.item_id)
        .subquery()
    )
    if available_only:
        query = (
            query.outerjoin(open_loan_sums, open_loan_sums.c.loan_item_id == InventoryItem.id)
            .filter(func.coalesce(InventoryItem.quantity, 0) - func.coalesce(open_loan_sums.c.loaned, 0) > 0)
        )
    items = query.distinct().limit(min(limit, 500)).all()

    loans = _open_loan_totals(db, [item.id for item in items]) if items else {}
    for item in items:
        on_loan = loans.get(item.id, 0.0)
        # Attached to the instance so the from_attributes response model picks
        # them up without a second, hand-built serialisation path.
        item.on_loan_qty = on_loan
        item.available_qty = float(item.quantity or 0) - on_loan
    return items


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
