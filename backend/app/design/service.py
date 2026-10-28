"""Persisted design runs: model intake -> deterministic simulation -> inventory -> revision."""
from __future__ import annotations

import asyncio
import logging
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from sqlalchemy.orm import selectinload

from ..database import SessionLocal
from ..models import AgentChatMessage, AgentChatSession, AgentStep, AgentTask, AgentToolCall, Attachment, ExperimentCase, GeneratedContent, InventoryItem
from ..providers import get_ai_provider
from ..observability.usage import apply_usage_to_generated
from .brief import FIELDS, merge_facts
from .solver import solve_design

logger = logging.getLogger(__name__)
PROCESS_STARTED = datetime.now(timezone.utc).timestamp()
# Local background runner: IDs accepted by this process, including queued tasks.
ACTIVE_RUNS: set[int] = set()


def inventory_snapshot(db):
    rows = db.query(InventoryItem).options(selectinload(InventoryItem.coatings), selectinload(InventoryItem.loans)).all()
    return [{"id": item.id, "name": item.name, "category": item.category, "roc_mm": item.roc_mm,
             "roc_is_flat": item.roc_is_flat, "diameter_mm": item.diameter_mm,
             "focal_length_mm": item.focal_length_mm, "condition": item.effective_condition,
             "thickness_mm": item.thickness_mm, "dimensions": item.dimensions, "material": item.material,
             "cut_axis": item.cut_axis, "doping_pct": item.doping_pct,
             "available_quantity": max(0, (item.quantity or 0) - sum(loan.quantity for loan in item.loans if loan.returned_at is None)),
             "location": item.location, "raw_spec": item.raw_spec, "parse_confidence": item.parse_confidence,
             "coatings": [{key: getattr(band, key) for key in ["surface", "wl_min_nm", "wl_max_nm", "function", "value_type", "comparator", "value_pct"]} for band in item.coatings]}
            for item in rows]


def _progress(db, task, number, title, detail=""):
    for step in task.steps:
        if step.status == "running":
            step.status = "completed"
    step = AgentStep(task_id=task.id, step_index=number, title=title, status="running", rationale=detail)
    db.add(step)
    db.commit()
    db.refresh(task)


async def execute_design(task_id: int):
    db = SessionLocal()
    started = perf_counter()
    try:
        task = db.get(AgentTask, task_id)
        if not task or task.status != "pending":
            return
        task.status = "running"
        db.commit()
        request = db.query(AgentToolCall).filter_by(task_id=task.id, tool_name="design_request").one().input_json
        case = db.get(ExperimentCase, task.case_id)
        previous = (case.parameters or {}).get("design_facts", {})
        await asyncio.sleep(0)
        _progress(db, task, 1, "读取需求与晶体标签", "保留原话、单位、图片出处；不把模型猜测记为事实。")
        images = []
        for aid in request["attachment_ids"]:
            attachment = db.get(Attachment, aid)
            if attachment is None or attachment.case_id != case.id:
                raise RuntimeError("附件已移除或不属于当前案例，请重新选择。")
            mime = mimetypes.guess_type(attachment.filename)[0]
            if mime not in {"image/png", "image/jpeg", "image/webp"}:
                raise RuntimeError("设计标签识别支持 PNG、JPEG、WebP 图片。")
            images.append({"id": aid, "mime": mime, "data": Path(attachment.filepath).read_bytes()})
        inventory = inventory_snapshot(db)
        constraints = request.get("constraints", {})
        context = {"title": case.title if not previous else "", "message": task.goal,
                   "description": case.description or "" if not previous else "",
                   "existing_facts": previous, "explicit_constraints": constraints,
                   "inventory": inventory[:150]}
        # Include every explicitly bound item even in a large catalogue.
        bound_ids = {int(value) for key, value in {**{k: f["value"] for k, f in previous.items()}, **constraints}.items() if key.endswith("_inventory_id") and value is not None}
        context["inventory"] += [item for item in inventory[150:] if item["id"] in bound_ids]
        evidence = {key: context[key] for key in ["title", "message", "description"]}
        for item in inventory:
            if item["id"] in bound_ids:
                evidence[f"inventory:{item['id']}"] = item.get("raw_spec") or item["name"]
        extraction = await get_ai_provider().extract_design_facts(context, images)
        if not isinstance(extraction.get("facts"), list):
            raise RuntimeError("模型未返回可核对的需求字段，未覆盖原设计，请重试。")
        facts, changes, notes = merge_facts(previous, extraction, evidence, request["attachment_ids"])
        for key, value in constraints.items():
            old = facts.get(key, {}).get("value")
            if old != value:
                changes.append({"key": key, "before": old, "after": value, "quote": "用户在约束面板修改"})
            if value is None:
                facts.pop(key, None)
            else:
                facts[key] = {"value": value, "quote": "用户在约束面板指定", "source": "constraint_panel",
                              "label": FIELDS[key][0], "unit": FIELDS[key][1], "verification": "user_constraint"}
        # UI and audit use the accepted subset; raw bytes/credentials never persist here.
        db.add(AgentToolCall(task_id=task.id, tool_name="extract_design_facts", status="completed",
                             input_json={"attachment_ids": request["attachment_ids"]},
                             output_json={"facts": facts, "changes": changes, "notes": notes}))
        _progress(db, task, 2, "扫描腔镜、腔长与晶体位置", "ABCD 自洽腔模、晶体孔径、热透镜场景、泵浦成像。")
        design = await asyncio.to_thread(solve_design, facts, inventory)
        design["changes"] = changes
        design["intake_notes"] = notes
        design["inventory_snapshot_at"] = datetime.now(timezone.utc).isoformat()
        design["inventory_count"] = len(inventory)
        _progress(db, task, 3, "核对库存并整理设计版本", "匹配镀膜/曲率/口径、排除损坏与借出，生成采购规格与缺失参数清单。")
        summary = design.get("summary") or "已记录需求。补齐下方关键参数后，我会继续进行数值设计。"
        if design["issues"]:
            summary += "\n" + "\n".join(item["text"] for item in design["issues"])
        if design["questions"]:
            summary += "\n可进一步收敛的参数：" + "；".join(item["question"] for item in design["questions"][:4])
        content = GeneratedContent(case_id=case.id, content_type="plan", model=extraction.get("model"),
                                   prompt_version="engineering_design_v2", latency_ms=int((perf_counter() - started) * 1000),
                                   content={"title": f"{case.title} · 光路设计", "engineering_design": design, "summary": summary})
        db.add(content)
        apply_usage_to_generated(content, extraction)
        db.flush()
        db.refresh(case)
        parameters = {**(case.parameters or {}), "design_facts": facts}
        # Keep downstream reports and the existing physics tools grounded in accepted facts.
        for key, parameter in [("pump_wavelength_nm", "pump_nm"), ("laser_wavelength_nm", "wavelength_nm"), ("gain_material", "gain_medium")]:
            if key in facts:
                parameters[parameter] = facts[key]["value"]
        case.parameters = parameters
        if case.goal == "待通过设计对话明确" and facts.get("laser_wavelength_nm"):
            wave = facts["laser_wavelength_nm"]["value"]
            medium = facts.get("gain_material", {}).get("value", "待确认材料")
            case.goal = f"设计 {medium} 激光器，目标波长 {wave:g} nm；详见设计工作区。"
        if facts.get("cavity_type", {}).get("value") in {"linear", "ring", "bow-tie", "custom"}:
            case.cavity_type = facts["cavity_type"]["value"]
        task.status = "completed"
        task.final_content_id = content.id
        for step in task.steps:
            step.status = "completed"
        db.add(AgentToolCall(task_id=task.id, tool_name="optical_design_solver", status="completed",
                             input_json={"fact_count": len(facts), "inventory_count": len(inventory)},
                             output_json={"search": design.get("search"), "status": design["status"], "content_id": content.id}))
        db.add(AgentChatMessage(session_id=request["session_id"], role="assistant", content=summary,
                                metadata_json={"design_run_id": task.id, "generated_content_id": content.id}))
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Design run %s failed", task_id)
        task = db.get(AgentTask, task_id)
        if task:
            task.status = "failed"
            # Provider exceptions can include request bodies. Keep them out of UI.
            message = str(exc) if isinstance(exc, RuntimeError) else f"设计计算失败（{type(exc).__name__}），原设计已保留。检查输入或模型连接后重试。"
            for step in task.steps:
                if step.status == "running":
                    step.status = "failed"
                    step.result_summary = message[:1000]
            db.commit()
    finally:
        ACTIVE_RUNS.discard(task_id)
        db.close()


def design_session(db, case, user_id=None):
    sid = (case.parameters or {}).get("design_session_id")
    session = db.get(AgentChatSession, sid) if sid else None
    if session is None or session.case_id != case.id:
        session = AgentChatSession(case_id=case.id, user_id=user_id, title=f"设计工作区 · {case.title}"[:255])
        db.add(session)
        db.flush()
        case.parameters = {**(case.parameters or {}), "design_session_id": session.id}
    return session
