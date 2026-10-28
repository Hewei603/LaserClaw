"""Workbook importer: lab xlsx -> normalized inventory rows + import report.

Understands the observed lab workbook layout:

- Sheet 1 (mirrors/optics): header row, columns
  序号 | 物料名称 | S1镀膜 | S2镀膜 | 规格 | 焦距或曲率半径 | 数量 | 存放地 | 保管人 | 厂商
  with 物料名称/规格 forward-filled inside groups (blank = same as above).
- Sheet 2 (crystals): no header, columns
  名称 | S1镀膜 | S2镀膜 | 尺寸/切向/掺杂 | (空) | 数量 | 存放地 | 保管人 | 厂商

Every row keeps its raw text; ambiguous rows land in the review queue
(``parse_confidence != 'parsed'``) instead of being guessed at.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from collections import defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, selectinload

from ..models import CoatingSpec, InventoryItem
from .parser import (
    DAMAGE_MARKERS,
    classify_category,
    parse_coating,
    parse_geometry,
)


@dataclass
class ImportReport:
    total_rows: int = 0
    imported: int = 0
    needs_review: int = 0
    partial: int = 0
    skipped_empty: int = 0
    coating_bands: int = 0
    review_queue: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_rows": self.total_rows,
            "imported": self.imported,
            "needs_review": self.needs_review,
            "partial": self.partial,
            "skipped_empty": self.skipped_empty,
            "coating_bands": self.coating_bands,
            "review_queue": self.review_queue[:50],
        }


def _cell(row: tuple, i: int) -> str:
    v = row[i] if i < len(row) else None
    return "" if v is None else str(v).strip()


def _to_float(text: str) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _material_from_name(name: str) -> str | None:
    import re
    m = re.search(r"(Nd|Yb|Er|Tm)\s*[:：]\s*([A-Za-z0-9]+)", name)
    if m:
        return f"{m.group(1)}:{m.group(2)}"
    for token in ("LBO", "KTP", "BBO", "BIBO", "KDP", "CaF2", "YAG", "YLF", "YVO4"):
        if token in name.upper():
            return token
    return None


def _build_item(
    db: Session,
    report: ImportReport,
    *,
    name: str,
    s1: str,
    s2: str,
    geometry_cells: tuple[str, ...],
    quantity: str,
    location: str,
    keeper: str,
    vendor: str,
    source_file: str,
) -> None:
    p1 = parse_coating(s1, "S1")
    p2 = parse_coating(s2, "S2")
    geo = parse_geometry(*geometry_cells)

    notes = [*p1.notes, *p2.notes, *geo.notes]
    confidences = {p1.confidence, p2.confidence}
    if "needs_review" in confidences and not (p1.bands or p2.bands):
        confidence = "needs_review"
    elif "needs_review" in confidences or "partial" in confidences:
        confidence = "partial"
    else:
        confidence = "parsed"

    # A geometry cell with content that produced NO structured field is silent
    # data loss: the evaluator would call the ROC "unknown" and send the student
    # to measure a number the workbook already states. Regex coverage will never
    # be complete, so the failure must at least be visible in the review queue.
    geometry_text = " ".join(c for c in geometry_cells if c).strip()
    geo_extracted = any([
        geo.roc_mm is not None, geo.roc_is_flat, geo.focal_length_mm is not None,
        geo.diameter_mm is not None, geo.thickness_mm is not None, geo.dimensions,
        geo.cut_angle_theta_deg is not None, geo.cut_angle_phi_deg is not None,
        geo.cut_axis, geo.doping_pct is not None,
    ])
    if geometry_text and not geo_extracted:
        notes.append(f"几何列未解析: {geometry_text[:60]}")
        if confidence == "parsed":
            confidence = "partial"

    condition = "ok"
    if any(marker in notes for marker in DAMAGE_MARKERS):
        condition = "damaged"
    elif any("未知" in n or "不能确定" in n or "未能确定" in n for n in notes):
        condition = "uncertain"

    raw_spec = " | ".join(filter(None, [f"S1:{s1}" if s1 else "", f"S2:{s2}" if s2 else "",
                                        *geometry_cells]))
    item = InventoryItem(
        category=classify_category(name),
        name=name,
        diameter_mm=geo.diameter_mm,
        roc_mm=geo.roc_mm,
        roc_is_flat=geo.roc_is_flat,
        focal_length_mm=geo.focal_length_mm,
        thickness_mm=geo.thickness_mm,
        dimensions=geo.dimensions,
        cut_angle_theta_deg=geo.cut_angle_theta_deg,
        cut_angle_phi_deg=geo.cut_angle_phi_deg,
        cut_axis=geo.cut_axis,
        doping_pct=geo.doping_pct,
        material=_material_from_name(name),
        # a genuine 0 must survive; only a blank/unparseable cell defaults to 1
        quantity=1.0 if _to_float(quantity) is None else _to_float(quantity),
        location=location or None,
        keeper=keeper or None,
        vendor=vendor or None,
        raw_spec=raw_spec[:2000],
        parse_confidence=confidence,
        parse_notes=notes,
        condition=condition,
        source_file=source_file,
    )
    db.add(item)
    db.flush()
    for band in (*p1.bands, *p2.bands):
        db.add(CoatingSpec(
            item_id=item.id,
            surface=band.surface,
            wl_min_nm=band.wl_min_nm,
            wl_max_nm=band.wl_max_nm,
            function=band.function,
            value_type=band.value_type,
            comparator=band.comparator,
            value_pct=band.value_pct,
            raw_fragment=band.raw_fragment,
        ))
        report.coating_bands += 1

    report.imported += 1
    if confidence == "needs_review":
        report.needs_review += 1
        report.review_queue.append({"item_id": item.id, "name": name, "raw": raw_spec[:160], "notes": notes})
    elif confidence == "partial":
        report.partial += 1
        report.review_queue.append({"item_id": item.id, "name": name, "raw": raw_spec[:160], "notes": notes})


def import_workbook(db: Session, path: str | Path, *, source_file: str | None = None) -> ImportReport:
    """Import the lab inventory workbook.  Returns an :class:`ImportReport`.

    Requires ``openpyxl``; raises ``RuntimeError`` with a clear message if the
    dependency is missing.
    """
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Inventory import requires the 'openpyxl' package") from exc

    path = Path(path)
    src = source_file or path.name
    wb = openpyxl.load_workbook(path, data_only=True)
    # Normal-mode worksheets are materialized; close the underlying archive
    # now so a failed refresh can remove its staged workbook on Windows too.
    wb.close()
    report = ImportReport()

    # Sheet 1: mirrors (header row 0; forward-filled name/size groups)
    ws = wb.worksheets[0]
    last_name = ""
    last_size = ""
    for idx, row in enumerate(ws.iter_rows(values_only=True)):
        if idx == 0:
            continue
        report.total_rows += 1
        raw_name = _cell(row, 1)
        s1, s2 = _cell(row, 2), _cell(row, 3)
        roc = _cell(row, 5)
        # Test the RAW cells: with forward-fill, `name` is non-empty from the
        # second row on, so an interior blank separator row would otherwise be
        # imported as a phantom duplicate of the previous item.
        if not any([raw_name, s1, s2, roc, _cell(row, 4), _cell(row, 6)]):
            report.skipped_empty += 1
            continue
        name = raw_name or last_name
        size = _cell(row, 4) or last_size
        last_name, last_size = name, size
        _build_item(
            db, report,
            name=name or "未命名镜片",
            s1=s1, s2=s2,
            geometry_cells=(size, roc),
            quantity=_cell(row, 6), location=_cell(row, 7),
            keeper=_cell(row, 8), vendor=_cell(row, 9),
            source_file=src,
        )

    # Sheet 2: crystals (no header row)
    if len(wb.worksheets) > 1:
        for row in wb.worksheets[1].iter_rows(values_only=True):
            name = _cell(row, 0)
            if not name:
                report.skipped_empty += 1
                continue
            report.total_rows += 1
            _build_item(
                db, report,
                name=name,
                s1=_cell(row, 1), s2=_cell(row, 2),
                geometry_cells=(_cell(row, 3),),
                quantity=_cell(row, 5), location=_cell(row, 6),
                keeper=_cell(row, 7), vendor=_cell(row, 8),
                source_file=src,
            )

    return report


class InventoryRefreshConflict(ValueError):
    """A workbook edit cannot be matched to recorded physical items safely."""


def refresh_workbook(db: Session, path: str | Path, *, source_file: str) -> ImportReport:
    """Refresh parsed fields without replacing item IDs or human history.

    A spec variant is identified by its name and original optical spec, never
    by its row position (sorting Excel must not transfer a damage verdict).
    Logistics disambiguate duplicate variants. If a protected row's identity
    becomes ambiguous, the API rolls back the entire refresh.
    """
    previous = (
        db.query(InventoryItem)
        .options(selectinload(InventoryItem.loans), selectinload(InventoryItem.coatings))
        .filter(InventoryItem.source_file == source_file)
        .order_by(InventoryItem.id).all()
    )
    previous_ids = {item.id for item in previous}
    report = import_workbook(db, path, source_file=source_file)
    db.flush()
    incoming = (
        db.query(InventoryItem).options(selectinload(InventoryItem.coatings))
        .filter(InventoryItem.source_file == source_file, InventoryItem.id.not_in(previous_ids))
        .order_by(InventoryItem.id).all()
    )

    def identity(item):
        return (item.category, item.name.strip(), (item.raw_spec or "").strip())

    def logistics(item):
        return (item.location, item.keeper, item.vendor)

    def protected(item):
        return item.condition_manual is not None or bool(item.loans)

    old_groups, new_groups = defaultdict(list), defaultdict(list)
    for item in previous:
        old_groups[identity(item)].append(item)
    for item in incoming:
        new_groups[identity(item)].append(item)

    matched_ids, remapped_ids = set(), {}
    excluded = {"id", "created_at", "updated_at", "condition_manual", "condition_note",
                "condition_marked_by", "condition_marked_at"}
    for key, new_items in new_groups.items():
        remaining = list(old_groups[key])
        ambiguous = len(remaining) > 1 or len(new_items) > 1
        if ambiguous and any(protected(item) for item in remaining):
            old_logistics = [logistics(item) for item in remaining]
            new_logistics = [logistics(item) for item in new_items]
            if (len(set(old_logistics)) != len(old_logistics)
                    or len(set(new_logistics)) != len(new_logistics)
                    or any(logistics(item) not in new_logistics for item in remaining if protected(item))):
                raise InventoryRefreshConflict(f"元件「{key[1]}」有重复规格且无法对应人工标记或借用历史，请保留可区分的存放地/保管人后重试。")
        for fresh in new_items:
            candidates = [item for item in remaining if logistics(item) == logistics(fresh)]
            old = candidates[0] if candidates else (remaining[0] if remaining and not ambiguous else None)
            if old is None and remaining and not any(protected(item) for item in remaining):
                old = remaining[0]
            if old is None:
                continue
            remaining.remove(old)
            for column in InventoryItem.__table__.columns:
                if column.name not in excluded:
                    setattr(old, column.name, getattr(fresh, column.name))
            old.coatings = list(fresh.coatings)
            matched_ids.add(old.id)
            remapped_ids[fresh.id] = old.id
            db.delete(fresh)

    unmatched_new = [item for item in incoming if item.id not in remapped_ids]
    for old in previous:
        if old.id in matched_ids:
            continue
        if protected(old):
            if any(item.name == old.name for item in unmatched_new):
                raise InventoryRefreshConflict(f"元件「{old.name}」的规格已改变，无法自动对应已有人工标记或借用历史；请核对清单中的名称和规格后重试。")
            # Removed rows with history remain inspectable, but cannot be
            # borrowed or recommended as stock that the new workbook omits.
            old.quantity = 0
            note = "未出现在最新导入清单中，库存置零并保留人工状态和借用历史。"
            old.parse_notes = list(dict.fromkeys([*(old.parse_notes or []), note]))
        else:
            db.delete(old)
    for row in report.review_queue:
        row["item_id"] = remapped_ids.get(row["item_id"], row["item_id"])
    db.flush()
    return report
