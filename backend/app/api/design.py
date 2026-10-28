"""Design workspace API. Uses existing case, conversation and artifact storage."""
from __future__ import annotations

import csv
import io
import json
from typing import Any, Literal
from datetime import timezone
from threading import Lock

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from ..auth.acl import assert_case_edit, assert_case_view
from ..auth.security import Principal, get_current_principal
from ..database import get_db
from ..design import service
from ..design.brief import validate_fact
from ..design.rezonator import cold_cavity_schema
from ..design.analysis import analyze_design, probe_design
from ..models import AgentChatMessage, AgentTask, AgentToolCall, Attachment, GeneratedContent
from ..schemas import GeneratedContentResponse
from .cases import get_case_or_404

router = APIRouter()
_start_lock = Lock()


class DesignRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    attachment_ids: list[int] = Field(default_factory=list, max_length=4)
    constraints: dict[str, Any] = Field(default_factory=dict, max_length=60)

    @field_validator("constraints")
    @classmethod
    def validate_constraints(cls, value):
        return {key: validate_fact(key, val) for key, val in value.items()}


class AnalysisRequest(BaseModel):
    candidate: int = Field(default=1, ge=1, le=5)
    mode: Literal["cavity", "pump"] = "cavity"
    output_gap_mm: float | None = Field(default=None, ge=.001, le=2000, allow_inf_nan=False)
    thermal_f_mm: float | None = Field(default=None, ge=1, le=1e7, allow_inf_nan=False)
    samples: int = Field(default=900, ge=100, le=5000)
    scan_samples: int = Field(default=600, ge=100, le=2000)


class ProbeRequest(AnalysisRequest):
    z_mm: float = Field(allow_inf_nan=False)


def _analysis_artifact(case_id, content_id, rank, db, principal):
    case = get_case_or_404(case_id, db)
    assert_case_view(db, case, principal)
    content = db.get(GeneratedContent, content_id)
    if not content or content.case_id != case_id:
        raise HTTPException(404, "设计版本不存在")
    design = content.content.get("engineering_design", {})
    candidates = design.get("candidates", [])
    if not 1 <= rank <= len(candidates):
        raise HTTPException(404, "候选方案不存在")
    return design, candidates[rank - 1]


@router.post("/{case_id}/design/{content_id}/analysis")
def analyze_saved_design(case_id: int, content_id: int, request: AnalysisRequest,
                         db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    design, candidate = _analysis_artifact(case_id, content_id, request.candidate, db, principal)
    try:
        return analyze_design(design, candidate, **request.model_dump(exclude={"candidate"}))
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/{case_id}/design/{content_id}/probe")
def probe_saved_design(case_id: int, content_id: int, request: ProbeRequest,
                       db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    design, candidate = _analysis_artifact(case_id, content_id, request.candidate, db, principal)
    try:
        return probe_design(design, candidate, **request.model_dump(exclude={"candidate", "samples", "scan_samples"}))
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc


def _task_json(task):
    return {"id": task.id, "status": task.status, "goal": task.goal, "final_content_id": task.final_content_id,
            "steps": [{"title": step.title, "status": step.status, "detail": step.result_summary or step.rationale}
                      for step in sorted(task.steps, key=lambda step: step.step_index)]}


def _recover_interrupted(db, case_id):
    for task in db.query(AgentTask).filter(AgentTask.case_id == case_id, AgentTask.mode == "design",
                                        AgentTask.status.in_(["pending", "running"])).all():
        created = task.created_at.replace(tzinfo=timezone.utc).timestamp()
        if created < service.PROCESS_STARTED and task.id not in service.ACTIVE_RUNS:
            task.status = "failed"
            for step in task.steps:
                if step.status == "running":
                    step.status = "failed"
                    step.result_summary = "上次运行因后端重启中断，原设计保留，可重新发送需求。"
    db.commit()


@router.get("/{case_id}/design")
def get_design(case_id: int, db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    case = get_case_or_404(case_id, db)
    assert_case_view(db, case, principal)
    _recover_interrupted(db, case_id)
    sid = (case.parameters or {}).get("design_session_id")
    messages = db.query(AgentChatMessage).filter_by(session_id=sid).order_by(AgentChatMessage.id).all() if sid else []
    revisions = db.query(GeneratedContent).filter_by(case_id=case_id, content_type="plan").order_by(GeneratedContent.id.desc()).all()
    tasks = db.query(AgentTask).filter_by(case_id=case_id, mode="design").order_by(AgentTask.id.desc()).limit(10).all()
    return {"messages": [{"id": msg.id, "role": msg.role, "content": msg.content, "metadata": msg.metadata_json, "created_at": msg.created_at} for msg in messages],
            "revisions": [GeneratedContentResponse.model_validate(item).model_dump() for item in revisions if "engineering_design" in item.content],
            "runs": [_task_json(task) for task in tasks], "facts": (case.parameters or {}).get("design_facts", {}),
            "inventory": service.inventory_snapshot(db)}


@router.post("/{case_id}/design/runs", status_code=202)
def start_design(case_id: int, request: DesignRequest, background_tasks: BackgroundTasks,
                 db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    case = get_case_or_404(case_id, db)
    assert_case_edit(db, case, principal)
    if not request.message.strip():
        raise HTTPException(422, "请描述实验目标或要修改的条件。")
    attachments = db.query(Attachment).filter(Attachment.id.in_(request.attachment_ids)).all()
    if len(attachments) != len(set(request.attachment_ids)) or any(item.case_id != case_id for item in attachments):
        raise HTTPException(404, "图片附件不存在或不属于当前案例。")
    with _start_lock:
        _recover_interrupted(db, case_id)
        if db.query(AgentTask).filter(AgentTask.case_id == case_id, AgentTask.mode == "design", AgentTask.status.in_(["pending", "running"])).first():
            raise HTTPException(409, "当前案例正在计算，请等待完成后再修改需求。")
        session = service.design_session(db, case, principal.user_id)
        task = AgentTask(case_id=case_id, user_id=principal.user_id, goal=request.message.strip(), mode="design", status="pending")
        db.add(task)
        db.flush()
        db.add(AgentChatMessage(session_id=session.id, role="user", content=request.message.strip(),
                                metadata_json={"design_run_id": task.id, "attachment_ids": request.attachment_ids}))
        db.add(AgentToolCall(task_id=task.id, tool_name="design_request", status="completed",
                             input_json={"session_id": session.id, "attachment_ids": request.attachment_ids,
                                         "constraints": request.constraints}, output_json={}))
        service.ACTIVE_RUNS.add(task.id)
        try:
            db.commit()
        except Exception:
            service.ACTIVE_RUNS.discard(task.id)
            raise
        background_tasks.add_task(service.execute_design, task.id)
        return {"task_id": task.id, "status": "pending"}


@router.get("/{case_id}/design/{content_id}/positions.csv")
def export_positions(case_id: int, content_id: int, candidate: int = 1, db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    case = get_case_or_404(case_id, db)
    assert_case_view(db, case, principal)
    content = db.get(GeneratedContent, content_id)
    if not content or content.case_id != case_id:
        raise HTTPException(404, "设计版本不存在")
    candidates = content.content.get("engineering_design", {}).get("candidates", [])
    if not 1 <= candidate <= len(candidates):
        raise HTTPException(404, "候选方案不存在")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["元件", "z (mm，相对 M1 镀膜面)", "结束 z (mm)", "位置依据"])
    for row in candidates[candidate - 1]["positions"]:
        writer.writerow([row["name"], row.get("z_mm") if row.get("z_mm") is not None else "待补参数", row.get("end_z_mm", ""), row["basis"]])
    return Response("\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="design-{content_id}-candidate-{candidate}.csv"'})


@router.get("/{case_id}/design/{content_id}/bom.csv")
def export_bom(case_id: int, content_id: int, candidate: int = 1, db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    case = get_case_or_404(case_id, db)
    assert_case_view(db, case, principal)
    content = db.get(GeneratedContent, content_id)
    if not content or content.case_id != case_id:
        raise HTTPException(404, "设计版本不存在")
    candidates = content.content.get("engineering_design", {}).get("candidates", [])
    if not 1 <= candidate <= len(candidates):
        raise HTTPException(404, "候选方案不存在")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["元件", "需求规格", "最小有效通光口径 mm", "输出耦合率 %（候选非定值）", "库存判断", "规格匹配记录", "待核验记录"])
    for row in candidates[candidate - 1]["bom"]:
        writer.writerow([row["role"], row["spec"], row["min_clear_aperture_mm"], row["transmission_pct"] or "/".join(map(str, row["transmission_candidates_pct"])), row["status"],
                         "; ".join(f"#{item['id']} {item['name']}" for item in row["matched"]),
                         "; ".join(f"#{item['id']} {item['name']}: {', '.join(item['unknowns'])}" for item in row["needs_verification"])])
    return Response("\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="design-{content_id}-candidate-{candidate}-bom.csv"'})


@router.get("/{case_id}/design/{content_id}/cavity.rez")
def export_rezonator(case_id: int, content_id: int, candidate: int = 1, db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    case = get_case_or_404(case_id, db)
    assert_case_view(db, case, principal)
    content = db.get(GeneratedContent, content_id)
    if not content or content.case_id != case_id:
        raise HTTPException(404, "设计版本不存在")
    design = content.content.get("engineering_design", {})
    candidates = design.get("candidates", [])
    if not 1 <= candidate <= len(candidates):
        raise HTTPException(404, "候选方案不存在")
    wl = design.get("resolved_inputs", {}).get("laser_wavelength_nm") or design["facts"]["laser_wavelength_nm"]["value"]
    output = cold_cavity_schema(candidates[candidate - 1], wl)
    return Response(json.dumps(output, ensure_ascii=False, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="design-{content_id}-candidate-{candidate}-cold.rez"'})
