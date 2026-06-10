"""Case module API routes."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
import statistics
import subprocess
import sys
import uuid
import zipfile
from io import StringIO
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from ..auth.acl import assert_case_edit, assert_case_view
from ..auth.security import Principal, get_current_principal
from ..config import get_settings
from ..database import get_db
from ..knowledge.ingestion import create_generated_content_source
from ..models import CaseComponentItem, CaseModule, CaseModuleFile, ExperimentCase, GeneratedContent
from ..observability.audit import record_audit
from ..schemas import (
    CaseComponentItemCreate,
    CaseComponentItemResponse,
    CaseComponentItemUpdate,
    CaseModuleCreate,
    CaseModuleFileResponse,
    CaseModuleResponse,
    CaseModuleUpdate,
    ModuleRunRequest,
)

router = APIRouter()
settings = get_settings()

MODULE_LABELS = {
    "stability": "Stability measurement",
    "beam_profile": "Beam profile analysis",
    "spectrum": "Spectrum analysis",
    "components": "Case component list",
}
MODULE_EXTENSIONS = {".zip", ".csv", ".txt", ".tsv", ".json", ".jpg", ".jpeg", ".png", ".bmp", ".pdf", ".npy"}


def _get_case_or_404(db: Session, case_id: int) -> ExperimentCase:
    case = db.query(ExperimentCase).filter(ExperimentCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Case {case_id} does not exist")
    return case


def _assert_module_view(db: Session, module: CaseModule, principal: Principal) -> None:
    case = _get_case_or_404(db, module.case_id)
    assert_case_view(db, case, principal)


def _assert_module_edit(db: Session, module: CaseModule, principal: Principal) -> None:
    case = _get_case_or_404(db, module.case_id)
    assert_case_edit(db, case, principal)


def _get_module_or_404(db: Session, module_id: int) -> CaseModule:
    module = db.query(CaseModule).filter(CaseModule.id == module_id).first()
    if not module:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Case module {module_id} does not exist")
    return module


def _module_upload_path(module_id: int, filename: str) -> tuple[str, str]:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in MODULE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported module file type. Allowed: {', '.join(sorted(MODULE_EXTENSIONS))}",
        )
    safe_name = f"{uuid.uuid4()}{ext}"
    root = os.path.abspath(os.path.join(settings.upload_dir, "case_modules", str(module_id)))
    filepath = os.path.abspath(os.path.join(root, safe_name))
    if not filepath.startswith(root):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid module upload path")
    return safe_name, filepath


def _merge_config(module: CaseModule, override: dict[str, Any] | None = None) -> dict[str, Any]:
    config = dict(module.config_json or {})
    if override:
        config.update(override)
    return config


def _first_file(module: CaseModule, extensions: set[str] | None = None, role: str = "input") -> CaseModuleFile | None:
    for item in module.files:
        if item.file_role != role:
            continue
        ext = os.path.splitext(item.filename)[1].lower()
        if extensions is None or ext in extensions:
            return item
    return None


def _save_output_file(db: Session, module: CaseModule, filepath: str, filename: str, file_type: str, metadata: dict[str, Any] | None = None) -> None:
    if not os.path.exists(filepath):
        return
    with open(filepath, "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    db.add(
        CaseModuleFile(
            module_id=module.id,
            filename=filename,
            filepath=os.path.abspath(filepath),
            file_type=file_type,
            file_role="output",
            content_hash=digest,
            metadata_json=metadata or {},
        )
    )


def _save_module_generated_content(db: Session, module: CaseModule, result: dict[str, Any]) -> GeneratedContent:
    content = {
        "title": module.title,
        "module_id": module.id,
        "module_type": module.module_type,
        "result": result,
    }
    generated = GeneratedContent(
        case_id=module.case_id,
        content_type=f"module_{module.module_type}",
        content=content,
        prompt_version="case_module_v1",
    )
    db.add(generated)
    db.flush()
    create_generated_content_source(db, generated)
    return generated


def _analyze_spectrum(module: CaseModule) -> dict[str, Any]:
    data_file = _first_file(module, {".csv", ".txt", ".tsv"})
    if not data_file:
        return {"status": "needs_input", "message": "Upload a spectrum data CSV/TXT file before running analysis."}

    delimiter = "\t" if os.path.splitext(data_file.filename)[1].lower() == ".tsv" else ","
    with open(data_file.filepath, "r", encoding="utf-8", errors="ignore") as handle:
        sample = handle.read()
    rows = list(csv.reader(StringIO(sample), delimiter=delimiter))
    if len(rows) < 2:
        return {"status": "failed", "message": "Spectrum file does not contain enough rows."}

    header = [cell.strip().lower() for cell in rows[0]]
    x_index = next((i for i, name in enumerate(header) if any(key in name for key in ["wave", "lambda", "nm"])), 0)
    y_index = next((i for i, name in enumerate(header) if any(key in name for key in ["intensity", "power", "counts", "signal"])), 1 if len(header) > 1 else 0)
    points: list[tuple[float, float]] = []
    for row in rows[1:]:
        try:
            points.append((float(row[x_index]), float(row[y_index])))
        except (ValueError, IndexError):
            continue
    if not points:
        return {"status": "failed", "message": "No numeric wavelength/intensity rows were found."}

    peak_wavelength, peak_intensity = max(points, key=lambda item: item[1])
    total = sum(max(y, 0.0) for _, y in points)
    center = sum(x * max(y, 0.0) for x, y in points) / total if total else peak_wavelength
    half = peak_intensity / 2.0
    above_half = [x for x, y in points if y >= half]
    fwhm = max(above_half) - min(above_half) if len(above_half) >= 2 else None
    return {
        "status": "completed",
        "input_file_id": data_file.id,
        "points": len(points),
        "x_column": rows[0][x_index] if rows[0] else f"column_{x_index + 1}",
        "y_column": rows[0][y_index] if rows[0] else f"column_{y_index + 1}",
        "peak_wavelength": round(peak_wavelength, 6),
        "peak_intensity": round(peak_intensity, 6),
        "center_wavelength": round(center, 6),
        "fwhm": round(fwhm, 6) if fwhm is not None else None,
        "wavelength_min": round(min(x for x, _ in points), 6),
        "wavelength_max": round(max(x for x, _ in points), 6),
        "summary": "Spectrum CSV was parsed and basic peak/FWHM metrics were calculated.",
    }


def _analyze_beam_profile(module: CaseModule) -> dict[str, Any]:
    image_file = _first_file(module, {".jpg", ".jpeg", ".png", ".bmp"})
    if not image_file:
        return {"status": "needs_input", "message": "Upload a BeamGage JPG/BMP/PNG export before running analysis."}
    result: dict[str, Any] = {
        "status": "completed",
        "input_file_id": image_file.id,
        "filename": image_file.filename,
        "summary": "BeamGage graphic was attached. Quantitative analysis is estimated unless raw numeric beam data is provided.",
        "analysis_level": "graphic_estimate",
    }
    try:
        from PIL import Image

        with Image.open(image_file.filepath) as img:
            width, height = img.size
        result.update(
            {
                "image_width_px": width,
                "image_height_px": height,
                "estimated_center_px": {"x": round(width / 2, 2), "y": round(height / 2, 2)},
                "estimated_horizontal_width_px": None,
                "estimated_vertical_width_px": None,
                "ellipticity": None,
            }
        )
    except Exception as exc:
        result["image_metadata_warning"] = str(exc)
    return result


def _run_stability(module: CaseModule, db: Session, config: dict[str, Any]) -> dict[str, Any]:
    zip_file = _first_file(module, {".zip"})
    if not zip_file:
        return {"status": "needs_input", "message": "Upload a ZIP of power meter photos before running stability analysis."}

    roi = config.get("roi")
    if isinstance(roi, str):
        roi_text = roi
    elif isinstance(roi, list) and len(roi) == 4:
        roi_text = ",".join(str(int(v)) for v in roi)
    else:
        return {
            "status": "needs_roi",
            "message": "Provide ROI as x,y,w,h. Automatic ROI detection is planned, but manual ROI is required for this run.",
            "input_file_id": zip_file.id,
        }

    app_path = Path(__file__).resolve().parents[3] / "PowerMeterReader_App" / "PowerMeterReader.py"
    if not app_path.exists():
        return {"status": "failed", "message": "PowerMeterReader_App/PowerMeterReader.py was not found."}

    output_root = Path(settings.upload_dir).resolve() / "case_modules" / str(module.id) / f"stability_{uuid.uuid4().hex[:8]}"
    output_root.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(app_path),
        "--cli",
        zip_file.filepath,
        "--out",
        str(output_root),
        "--roi",
        roi_text,
        "--min",
        str(config.get("valid_min", 90)),
        "--max",
        str(config.get("valid_max", 130)),
        "--ylabel",
        str(config.get("ylabel", "Power")),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=300)
    if completed.returncode != 0:
        return {
            "status": "failed",
            "message": "PowerMeterReader failed.",
            "stdout": completed.stdout[-2000:],
            "stderr": completed.stderr[-2000:],
        }

    result_dirs = [item for item in output_root.iterdir() if item.is_dir()]
    result_dir = max(result_dirs, key=lambda item: item.stat().st_mtime) if result_dirs else output_root
    outputs = {
        "pdf": result_dir / "power_meter_report.pdf",
        "csv": result_dir / "power_meter_readings.csv",
        "plot": result_dir / "power_plot.png",
        "npy": result_dir / "power_meter_readings.npy",
    }
    for key, path in outputs.items():
        media_type = {
            "pdf": "application/pdf",
            "csv": "text/csv",
            "plot": "image/png",
            "npy": "application/octet-stream",
        }[key]
        _save_output_file(db, module, str(path), path.name, media_type, {"output_type": key})

    readings: list[float] = []
    if outputs["csv"].exists():
        with open(outputs["csv"], "r", encoding="utf-8", errors="ignore") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                for key in ["Power", "Value", "value", "power"]:
                    try:
                        if row.get(key):
                            readings.append(float(row[key]))
                            break
                    except ValueError:
                        pass
    stats = {
        "count": len(readings),
        "mean": round(statistics.mean(readings), 6) if readings else None,
        "min": round(min(readings), 6) if readings else None,
        "max": round(max(readings), 6) if readings else None,
        "stdev": round(statistics.stdev(readings), 6) if len(readings) > 1 else None,
        "rms": round(math.sqrt(sum(value * value for value in readings) / len(readings)), 6) if readings else None,
    }
    return {
        "status": "completed",
        "input_file_id": zip_file.id,
        "roi": roi_text,
        "valid_min": config.get("valid_min", 90),
        "valid_max": config.get("valid_max", 130),
        "output_dir": str(result_dir),
        "stats": stats,
        "summary": "Power meter OCR stability analysis completed.",
    }


def _component_seed_items(case: ExperimentCase, module_id: int) -> list[dict[str, Any]]:
    parameters = case.parameters or {}
    base = [
        ("instrument", "Laser safety eyewear", "OD and wavelength must match the experiment", "Required PPE"),
        ("instrument", "Power meter", "Appropriate sensor head and range", "Measure output and stability"),
        ("instrument", "Beam viewer or BeamGage camera", "Compatible wavelength and attenuation", "Record beam profile"),
        ("optic", "Beam dumps", "Rated for expected wavelength and power", "Terminate all beams safely"),
        ("mount", "Mirror mounts", "Stable kinematic mounts", "Cavity alignment"),
    ]
    if case.cavity_type in {"linear", "ring", "bow-tie", "custom"}:
        base.extend(
            [
                ("optic", "Input mirror", str(parameters.get("input_mirror", "coating/ROC TBD")), "Cavity input optic"),
                ("optic", "Output coupler", str(parameters.get("output_coupler", "transmission TBD")), "Cavity output optic"),
                ("crystal", "Gain medium", str(parameters.get("gain_medium", "material/length TBD")), "Laser gain element"),
            ]
        )
    return [
        {
            "case_id": case.id,
            "module_id": module_id,
            "category": category,
            "name": name,
            "specification": specification,
            "quantity": 1,
            "unit": "pcs",
            "purpose": purpose,
            "required": True,
            "owned": False,
            "procurement_status": "needed",
            "source": "agent_generated",
        }
        for category, name, specification, purpose in base
    ]


@router.post("/{case_id}/modules", response_model=CaseModuleResponse, status_code=status.HTTP_201_CREATED)
async def create_case_module(
    case_id: int,
    payload: CaseModuleCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Create an optional workflow module for a case."""
    case = _get_case_or_404(db, case_id)
    assert_case_edit(db, case, principal)
    module = CaseModule(
        case_id=case_id,
        module_type=payload.module_type,
        title=payload.title or MODULE_LABELS[payload.module_type],
        status="draft",
        config_json=payload.config_json,
        result_json={},
    )
    db.add(module)
    db.flush()
    record_audit(db, action="case_module.create", resource_type="case_module", resource_id=str(module.id))
    db.commit()
    db.refresh(module)
    return module


@router.get("/{case_id}/modules", response_model=list[CaseModuleResponse])
async def list_case_modules(
    case_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """List all optional workflow modules for a case."""
    case = _get_case_or_404(db, case_id)
    assert_case_view(db, case, principal)
    return db.query(CaseModule).filter(CaseModule.case_id == case_id).order_by(CaseModule.created_at.desc()).all()


@router.get("/modules/{module_id}", response_model=CaseModuleResponse)
async def get_case_module(
    module_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Get one case module."""
    module = _get_module_or_404(db, module_id)
    _assert_module_view(db, module, principal)
    return module


@router.patch("/modules/{module_id}", response_model=CaseModuleResponse)
async def update_case_module(
    module_id: int,
    payload: CaseModuleUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Update module metadata, config, or result JSON."""
    module = _get_module_or_404(db, module_id)
    _assert_module_edit(db, module, principal)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(module, field, value)
    record_audit(db, action="case_module.update", resource_type="case_module", resource_id=str(module.id))
    db.commit()
    db.refresh(module)
    return module


@router.delete("/modules/{module_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_case_module(
    module_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Delete a module and its owned files."""
    module = _get_module_or_404(db, module_id)
    _assert_module_edit(db, module, principal)
    module_dir = os.path.abspath(os.path.join(settings.upload_dir, "case_modules", str(module.id)))
    if os.path.isdir(module_dir):
        shutil.rmtree(module_dir)
    record_audit(db, action="case_module.delete", resource_type="case_module", resource_id=str(module.id))
    db.delete(module)
    db.commit()
    return None


@router.post("/modules/{module_id}/files", response_model=CaseModuleFileResponse, status_code=status.HTTP_201_CREATED)
async def upload_module_file(
    module_id: int,
    file_role: str = "input",
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Upload an input or reference file to a case module."""
    module = _get_module_or_404(db, module_id)
    _assert_module_edit(db, module, principal)
    _, filepath = _module_upload_path(module.id, file.filename or "")
    content = await file.read()
    if len(content) > settings.max_upload_size:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File exceeds max upload size")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "wb") as handle:
        handle.write(content)
    item = CaseModuleFile(
        module_id=module.id,
        filename=os.path.basename(file.filename or "module-file"),
        filepath=filepath,
        file_type=file.content_type,
        file_role=file_role,
        content_hash=hashlib.sha256(content).hexdigest(),
        metadata_json={},
    )
    module.status = "ready" if file_role == "input" and module.status == "draft" else module.status
    db.add(item)
    db.flush()
    record_audit(db, action="case_module.file.upload", resource_type="case_module_file", resource_id=str(item.id))
    db.commit()
    db.refresh(item)
    return item


@router.get("/module-files/{file_id}")
async def download_module_file(
    file_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Download a module input or output file."""
    item = db.query(CaseModuleFile).filter(CaseModuleFile.id == file_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Module file {file_id} does not exist")
    _assert_module_view(db, item.module, principal)
    if not os.path.exists(item.filepath):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module file is missing")
    return FileResponse(path=item.filepath, filename=item.filename, media_type=item.file_type)


@router.post("/modules/{module_id}/run", response_model=CaseModuleResponse)
async def run_case_module(
    module_id: int,
    payload: ModuleRunRequest = ModuleRunRequest(),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Run the module-specific analysis or generation workflow."""
    module = _get_module_or_404(db, module_id)
    _assert_module_edit(db, module, principal)
    config = _merge_config(module, payload.config_json)
    module.config_json = config
    module.status = "running"
    db.flush()

    if module.module_type == "stability":
        result = _run_stability(module, db, config)
    elif module.module_type == "spectrum":
        result = _analyze_spectrum(module)
    elif module.module_type == "beam_profile":
        result = _analyze_beam_profile(module)
    elif module.module_type == "components":
        case = _get_case_or_404(db, module.case_id)
        existing = db.query(CaseComponentItem).filter(CaseComponentItem.module_id == module.id).count()
        if existing == 0:
            for item in _component_seed_items(case, module.id):
                db.add(CaseComponentItem(**item))
        result = {"status": "completed", "summary": "Case component list generated from case context.", "generated_items": existing or 8}
    else:
        result = {"status": "failed", "message": f"Unsupported module type {module.module_type}"}

    module.result_json = result
    module.status = "completed" if result.get("status") == "completed" else result.get("status", "failed")
    if payload.save_generated_content:
        generated = _save_module_generated_content(db, module, result)
        result["generated_content_id"] = generated.id
        module.result_json = result
    record_audit(db, action="case_module.run", resource_type="case_module", resource_id=str(module.id))
    db.commit()
    db.refresh(module)
    return module


@router.get("/{case_id}/components", response_model=list[CaseComponentItemResponse])
async def list_component_items(
    case_id: int,
    module_id: int | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """List component/procurement items for one case."""
    case = _get_case_or_404(db, case_id)
    assert_case_view(db, case, principal)
    query = db.query(CaseComponentItem).filter(CaseComponentItem.case_id == case_id)
    if module_id is not None:
        query = query.filter(CaseComponentItem.module_id == module_id)
    return query.order_by(CaseComponentItem.category, CaseComponentItem.name).all()


@router.post("/{case_id}/components", response_model=CaseComponentItemResponse, status_code=status.HTTP_201_CREATED)
async def create_component_item(
    case_id: int,
    payload: CaseComponentItemCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Add one component/procurement item to a case."""
    case = _get_case_or_404(db, case_id)
    assert_case_edit(db, case, principal)
    item = CaseComponentItem(case_id=case_id, **payload.model_dump())
    db.add(item)
    db.flush()
    record_audit(db, action="case_component.create", resource_type="case_component_item", resource_id=str(item.id))
    db.commit()
    db.refresh(item)
    return item


@router.patch("/components/{item_id}", response_model=CaseComponentItemResponse)
async def update_component_item(
    item_id: int,
    payload: CaseComponentItemUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Update one component/procurement item."""
    item = db.query(CaseComponentItem).filter(CaseComponentItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Component item {item_id} does not exist")
    case = _get_case_or_404(db, item.case_id)
    assert_case_edit(db, case, principal)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    if payload.owned is True:
        item.procurement_status = "owned"
    record_audit(db, action="case_component.update", resource_type="case_component_item", resource_id=str(item.id))
    db.commit()
    db.refresh(item)
    return item


@router.delete("/components/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_component_item(
    item_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Delete one component/procurement item."""
    item = db.query(CaseComponentItem).filter(CaseComponentItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Component item {item_id} does not exist")
    case = _get_case_or_404(db, item.case_id)
    assert_case_edit(db, case, principal)
    record_audit(db, action="case_component.delete", resource_type="case_component_item", resource_id=str(item.id))
    db.delete(item)
    db.commit()
    return None


@router.get("/{case_id}/components/procurement.csv")
async def export_procurement_csv(
    case_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Export not-owned component items as a procurement CSV."""
    case = _get_case_or_404(db, case_id)
    assert_case_view(db, case, principal)
    items = (
        db.query(CaseComponentItem)
        .filter(CaseComponentItem.case_id == case_id, CaseComponentItem.owned == False)  # noqa: E712
        .order_by(CaseComponentItem.category, CaseComponentItem.name)
        .all()
    )
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["category", "name", "specification", "quantity", "unit", "purpose", "vendor", "part_number", "status", "notes"])
    for item in items:
        writer.writerow([
            item.category,
            item.name,
            item.specification,
            item.quantity,
            item.unit,
            item.purpose,
            item.vendor,
            item.part_number,
            item.procurement_status,
            item.notes,
        ])
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="case-{case_id}-procurement.csv"'},
    )
