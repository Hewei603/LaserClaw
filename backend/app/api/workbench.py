"""Task workbench: submit, inspect, stop and continue through ordinary replies."""
from datetime import timezone
from threading import Lock

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth.acl import assert_case_edit, assert_case_view
from ..auth.security import Principal, get_current_principal
from ..database import get_db
from ..models import AgentChatMessage, AgentTask, AgentToolCall, Attachment
from ..workbench import service
from ..workbench.tools import REGISTRY
from ..workbench.projects import SaveProject, read_project, revisions, save_project
from ..workbench.optics import OpticalScan2D, scan_system_2d
from ..models import GeneratedContent
from .cases import get_case_or_404

router = APIRouter()
_start_lock = Lock()


@router.get("/{case_id}/optical-project")
def get_project(case_id: int, revision_id: int | None = None, db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    case = get_case_or_404(case_id, db)
    assert_case_view(db, case, principal)
    try:
        current = read_project(db, case_id, revision_id)
        scan = None
        if current:
            for artifact in db.query(GeneratedContent).filter_by(case_id=case_id, content_type="optical_scan").order_by(GeneratedContent.id.desc()):
                if artifact.content.get("project_revision_id") == current["revision_id"]:
                    scan = {"artifact_id": artifact.id, **artifact.content["scan"]}
                    break
        return {"current": current, "scan": scan, "revisions": [{"id": r.id, "title": r.content["project"]["title"], "change_note": r.content["change_note"], "created_at": r.generated_at} for r in revisions(db, case_id)]}
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/{case_id}/optical-project")
def update_project(case_id: int, request: SaveProject, db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    case = get_case_or_404(case_id, db)
    assert_case_edit(db, case, principal)
    try:
        # A user editing the UI can explicitly check the unlock option. Agent saves
        # use the separate dispatcher and must provide evidence from its user turn.
        return save_project(db, case_id, request, allow_unlock=request.unlock_quote == "用户在工程编辑器明确解锁")
    except ValueError as exc:
        raise HTTPException(409 if "changed since" in str(exc) else 422, str(exc)) from exc


@router.post("/{case_id}/optical-project/{revision_id}/scan-2d")
def scan_project(case_id: int, revision_id: int, request: OpticalScan2D, db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    case = get_case_or_404(case_id, db)
    assert_case_edit(db, case, principal)
    try:
        saved = read_project(db, case_id, revision_id)
        if request.system.model_dump() != saved["project"]["system"]:
            raise ValueError("Save the changed project before scanning; scan must match its revision")
        output = scan_system_2d(request)
        artifact = GeneratedContent(case_id=case_id, content_type="optical_scan", prompt_version="optical-map-v1", content={"project_revision_id": revision_id, "configuration": request.model_dump(), "scan": output, "summary": "光学工程二维稳定图"})
        db.add(artifact)
        db.commit()
        return {"artifact_id": artifact.id, **output}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class RunRequest(BaseModel):
    message: str = Field(min_length=1, max_length=24000)
    attachment_ids: list[int] = Field(default_factory=list, max_length=8)


def recover(db, case_id):
    for task in db.query(AgentTask).filter(AgentTask.case_id == case_id, AgentTask.mode == "workbench", AgentTask.status.in_(["pending", "running"])).all():
        if task.id not in service.ACTIVE_RUNS and task.created_at.replace(tzinfo=timezone.utc).timestamp() < service.PROCESS_STARTED:
            task.status = "failed"
            for step in task.steps:
                if step.status == "running":
                    step.status, step.result_summary = "failed", "运行被服务重启中断，已有工具结果保留，可以继续。"
            for call in task.tool_calls:
                if call.status == "running":
                    call.status, call.error_message = "failed", "运行被服务重启中断。"
    db.commit()


def task_json(task, include_tools=True):
    return {"id": task.id, "goal": task.goal, "status": task.status, "created_at": task.created_at,
            "final_content_id": task.final_content_id, "active": task.id in service.ACTIVE_RUNS,
            "tools_loaded": include_tools,
            "result": task.final_content.content.get("workbench") if task.final_content else None,
            "steps": [{"title": s.title, "status": s.status, "purpose": s.rationale, "summary": s.result_summary} for s in task.steps],
            "tools": [{"id": c.id, "name": c.tool_name, "status": c.status, "input": c.input_json,
                       "output": c.output_json, "error": c.error_message, "latency_ms": c.latency_ms}
                      for c in sorted(task.tool_calls, key=lambda c: c.id) if c.tool_name != "workbench_request"] if include_tools else []}


@router.get("/{case_id}/workbench")
def get_workbench(case_id: int, db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    case = get_case_or_404(case_id, db)
    assert_case_view(db, case, principal)
    recover(db, case_id)
    sid = (case.parameters or {}).get("workbench_session_id") or (case.parameters or {}).get("design_session_id")
    messages = db.query(AgentChatMessage).filter_by(session_id=sid).order_by(AgentChatMessage.id).all() if sid else []
    tasks = db.query(AgentTask).filter_by(case_id=case_id, mode="workbench").order_by(AgentTask.id.desc()).limit(25).all()
    return {"messages": [{"id": m.id, "role": m.role, "content": m.content, "metadata": m.metadata_json} for m in messages],
            "runs": [task_json(task, include_tools=(index == 0)) for index, task in enumerate(tasks)],
            "capabilities": [{"name": name, "description": desc} for name, (_, desc) in REGISTRY.items() if name != "finish"],
            "attachments": [{"id": a.id, "filename": a.filename} for a in case.attachments]}


@router.get("/{case_id}/workbench/runs/{task_id}")
def get_run(case_id: int, task_id: int, db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    case = get_case_or_404(case_id, db)
    assert_case_view(db, case, principal)
    task = db.get(AgentTask, task_id)
    if not task or task.case_id != case_id or task.mode != "workbench":
        raise HTTPException(404, "任务不存在")
    return task_json(task)


@router.post("/{case_id}/workbench/runs", status_code=202)
def start_run(case_id: int, request: RunRequest, background_tasks: BackgroundTasks,
              db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    case = get_case_or_404(case_id, db)
    assert_case_edit(db, case, principal)
    if not request.message.strip():
        raise HTTPException(422, "请描述目标、现有信息或回复 Agent 的问题。")
    attachments = db.query(Attachment).filter(Attachment.id.in_(request.attachment_ids)).all()
    if len(attachments) != len(set(request.attachment_ids)) or any(a.case_id != case_id for a in attachments):
        raise HTTPException(404, "附件不存在或不属于当前案例。")
    with _start_lock:
        recover(db, case_id)
        if db.query(AgentTask).filter(AgentTask.case_id == case_id, AgentTask.id.in_(list(service.ACTIVE_RUNS))).first():
            raise HTTPException(409, "上一轮仍在结束当前调用，请稍后继续，已有结果会保留。")
        if db.query(AgentTask).filter(AgentTask.case_id == case_id, AgentTask.mode.in_(["workbench", "design"]), AgentTask.status.in_(["pending", "running"])).first():
            raise HTTPException(409, "此案例正在运行，请完成或停止当前任务后继续。")
        session = service.session_for_case(db, case, principal.user_id)
        task = AgentTask(case_id=case_id, user_id=principal.user_id, mode="workbench", goal=request.message.strip(), status="pending")
        db.add(task)
        db.flush()
        db.add(AgentChatMessage(session_id=session.id, role="user", content=task.goal,
                                metadata_json={"workbench_run_id": task.id, "attachment_ids": request.attachment_ids}))
        db.add(AgentToolCall(task_id=task.id, tool_name="workbench_request", input_json={"session_id": session.id, "attachment_ids": request.attachment_ids}, output_json={}))
        service.ACTIVE_RUNS.add(task.id)
        try:
            db.commit()
        except Exception:
            service.ACTIVE_RUNS.discard(task.id)
            raise
        background_tasks.add_task(service.execute_run, task.id)
        return {"task_id": task.id, "status": task.status}


@router.post("/{case_id}/workbench/runs/{task_id}/stop")
def stop_run(case_id: int, task_id: int, db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    case = get_case_or_404(case_id, db)
    assert_case_edit(db, case, principal)
    task = db.get(AgentTask, task_id)
    if not task or task.case_id != case_id or task.mode != "workbench":
        raise HTTPException(404, "任务不存在")
    if task.status in {"pending", "running"}:
        task.status = "cancelled"
        db.commit()
    return {"task_id": task.id, "status": task.status}
