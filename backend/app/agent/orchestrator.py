"""Stateful Agent orchestrator."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..knowledge.ingestion import create_generated_content_source
from ..inventory.evaluator import evaluate_candidates
from ..models import AgentStep, AgentTask, CaseModule, ExperimentCase, GeneratedContent
from ..observability.audit import record_audit
from ..observability.usage import apply_usage_to_generated
from ..providers import get_ai_provider
from .guardrails import assess_risk
from .planner import build_plan
from .tools import (
    get_case_payload,
    create_case_module_payload,
    generate_component_items_payload,
    list_attachments_payload,
    list_case_modules_payload,
    list_generated_contents_payload,
    record_tool_call,
    run_physics_tool_payload,
    save_generated_content_payload,
    search_payload,
)

logger = logging.getLogger(__name__)
PHYSICS_MODES = {"cavity_design", "phase_match", "coating_tmm"}
MODULE_MODES = {"stability", "beam_profile", "spectrum", "components", "module_management", "component_match", "power_curve"} | PHYSICS_MODES


async def create_and_run_task(
    db: Session,
    *,
    case_id: int | None,
    goal: str,
    mode: str,
    require_citations: bool = True,
    extra_context: dict[str, Any] | None = None,
) -> AgentTask:
    """Create a task and run the MVP Agent flow synchronously."""
    case = None
    if case_id is not None:
        case = db.query(ExperimentCase).filter(ExperimentCase.id == case_id).first()
        if not case:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Case {case_id} does not exist")

    risk_level, safety_notes = assess_risk(goal)
    task = AgentTask(case_id=case_id, goal=goal, mode=mode, risk_level=risk_level, status="running")
    db.add(task)
    db.flush()

    steps = []
    for index, spec in enumerate(build_plan(mode), start=1):
        step = AgentStep(task_id=task.id, step_index=index, title=spec["title"], rationale=spec["rationale"], status="pending")
        db.add(step)
        steps.append(step)
    db.flush()

    try:
        case_payload: dict[str, Any] = {}
        if case:
            case_payload = record_tool_call(
                db,
                task,
                steps[0].id,
                "get_case",
                {"case_id": case.id},
                lambda: get_case_payload(case),
            )
            record_tool_call(db, task, steps[0].id, "list_attachments", {"case_id": case.id}, lambda: list_attachments_payload(case))
            record_tool_call(
                db,
                task,
                steps[0].id,
                "list_generated_contents",
                {"case_id": case.id},
                lambda: list_generated_contents_payload(case),
            )
        steps[0].status = "completed"
        steps[0].result_summary = "Case context loaded." if case else "No case was linked to this task."

        if case:
            record_tool_call(db, task, steps[0].id, "list_case_modules", {"case_id": case.id}, lambda: list_case_modules_payload(case))

        retrieval = record_tool_call(
            db,
            task,
            steps[1].id,
            "search_knowledge",
            {"query": goal, "case_id": case_id, "top_k": 5},
            lambda: search_payload(db, goal, case_id, 5, task.id),
        )
        steps[1].status = "completed"
        steps[1].result_summary = f"Retrieved {len(retrieval['results'])} knowledge chunks."

        if mode in MODULE_MODES:
            if case is None:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A case_id is required to run a module task")
            content = _run_module_task(db, task, steps, case, mode, goal, retrieval)
            generated = GeneratedContent(
                case_id=case.id,
                content_type=f"module_{content['module_type']}",
                content=content,
                prompt_version=f"agent_module_{mode}_v1",
            )
            apply_usage_to_generated(generated, content)
            db.add(generated)
            db.flush()
            create_generated_content_source(db, generated)
            record_tool_call(
                db,
                task,
                steps[3].id,
                "save_generated_content",
                {"case_id": case.id, "content_type": generated.content_type},
                lambda: save_generated_content_payload(generated),
            )
            steps[3].status = "completed"
            steps[3].result_summary = "Module result saved as generated content."
            task.status = "completed"
            task.final_content_id = generated.id
            record_audit(db, action="agent_task.complete", resource_type="agent_task", resource_id=str(task.id))
            db.commit()
            db.refresh(task)
            return task

        try:
            content = await _generate_artifact(mode, case_payload, goal, extra_context=extra_context or retrieval)
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Failed to generate Agent %s artifact", mode)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to generate {mode}: {exc}",
            ) from exc
        content["agent_task_id"] = task.id
        content["safety_notes"] = safety_notes
        content["risk_level"] = risk_level
        if require_citations:
            content["citations"] = retrieval["citations"]
            content["confidence"] = "medium" if retrieval["citations"] else "low"
        steps[2].status = "completed"
        steps[2].result_summary = f"Created {mode} draft."

        generated = GeneratedContent(
            case_id=case_id or 0,
            content_type=mode if mode != "plan" else "plan",
            content=content,
            prompt_version=f"agent_{mode}_v1",
        )
        apply_usage_to_generated(generated, content)
        if case_id is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A case_id is required to save an Agent artifact")
        db.add(generated)
        db.flush()
        create_generated_content_source(db, generated)
        record_tool_call(
            db,
            task,
            steps[3].id,
            "save_generated_content",
            {"case_id": case_id, "content_type": generated.content_type},
            lambda: save_generated_content_payload(generated),
        )
        steps[3].status = "completed"
        steps[3].result_summary = "Artifact saved as generated content."

        task.status = "completed"
        task.final_content_id = generated.id
        record_audit(db, action="agent_task.complete", resource_type="agent_task", resource_id=str(task.id))
        db.commit()
        db.refresh(task)
        return task
    except Exception:
        # Discard every partial write from this run (half-built modules,
        # component items, generated content, retrieval rows, and the original
        # flushed task/steps) instead of committing them alongside the failure.
        db.rollback()
        failed_task = AgentTask(
            case_id=case_id,
            goal=goal,
            mode=mode,
            risk_level=risk_level,
            status="failed",
        )
        db.add(failed_task)
        db.flush()
        record_audit(db, action="agent_task.failed", resource_type="agent_task", resource_id=str(failed_task.id))
        db.commit()
        raise


def _run_module_task(
    db: Session,
    task: AgentTask,
    steps: list[AgentStep],
    case: ExperimentCase,
    mode: str,
    goal: str,
    retrieval: dict[str, Any],
) -> dict[str, Any]:
    module_type = "components" if mode in {"components", "module_management"} else mode
    existing = (
        db.query(CaseModule)
        .filter(CaseModule.case_id == case.id, CaseModule.module_type == module_type)
        .order_by(CaseModule.created_at.desc())
        .first()
    )
    if existing is None:
        created = record_tool_call(
            db,
            task,
            steps[2].id,
            "create_case_module",
            {"case_id": case.id, "module_type": module_type},
            lambda: create_case_module_payload(db, case, module_type),
        )
        module = db.query(CaseModule).filter(CaseModule.id == created["module_id"]).first()
    else:
        module = existing

    if module is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Module creation failed")

    record_tool_call(
        db,
        task,
        steps[1].id,
        "get_case_module",
        {"module_id": module.id},
        lambda: {
            "module_id": module.id,
            "module_type": module.module_type,
            "status": module.status,
            "files": [{"id": item.id, "filename": item.filename, "role": item.file_role} for item in module.files],
        },
    )

    if module.module_type == "components":
        output = record_tool_call(
            db,
            task,
            steps[2].id,
            "generate_component_list",
            {"case_id": case.id, "module_id": module.id},
            lambda: generate_component_items_payload(db, case, module.id),
        )
        module.status = "completed"
        module.result_json = {
            "status": "completed",
            "summary": "Agent generated or refreshed the case component list.",
            "item_count": len(output["items"]),
        }
    elif module.module_type in PHYSICS_MODES:
        # Deterministic physics compute: case parameters overlaid by module config.
        merged_config = {**(case.parameters or {}), **(module.config_json or {})}
        output = record_tool_call(
            db,
            task,
            steps[2].id,
            f"compute_{module.module_type}",
            {"module_id": module.id, "config": merged_config},
            lambda: run_physics_tool_payload(module.module_type, merged_config),
        )
        module.status = output.get("status", "failed")
        module.result_json = output
    elif module.module_type == "component_match":
        # Deterministic L1 inventory evaluation against the case's requirement spec.
        stored_req = (case.parameters or {}).get("component_requirement")
        merged_config = {**(stored_req if isinstance(stored_req, dict) else {}),
                         **(module.config_json or {})}
        output = record_tool_call(
            db,
            task,
            steps[2].id,
            "match_components",
            {"module_id": module.id, "requirement": merged_config},
            lambda: evaluate_candidates(db, merged_config),
        )
        module.status = output.get("status", "failed")
        module.result_json = output
    else:
        output = record_tool_call(
            db,
            task,
            steps[2].id,
            "run_case_module_analysis",
            {"module_id": module.id, "mode": module.module_type},
            lambda: _module_needs_inputs_payload(module),
        )
        module.status = output["status"]
        module.result_json = output

    steps[2].status = "completed"
    steps[2].result_summary = module.result_json.get("summary") or module.result_json.get("message") or "Module workflow updated."
    return {
        "disclaimer": "Module output is an auditable workspace artifact. Experimental decisions still require qualified human review.",
        "agent_task_id": task.id,
        "module_id": module.id,
        "module_type": module.module_type,
        "title": module.title,
        "goal": goal,
        "result": module.result_json,
        "citations": retrieval.get("citations", []),
        "confidence": "medium" if retrieval.get("citations") else "low",
    }


def _module_needs_inputs_payload(module: CaseModule) -> dict[str, Any]:
    required = {
        "stability": "Upload a power meter photo ZIP and provide ROI x,y,w,h, then run the stability module.",
        "beam_profile": "Upload a BeamGage JPG/BMP/PNG export, then run the beam profile module.",
        "spectrum": "Upload a spectrum CSV/TXT data file, then run the spectrum module.",
        "power_curve": "Upload a two-column pump/output power CSV (or set config.data), then run the power curve module.",
    }
    if module.files:
        return {
            "status": "ready",
            "summary": "Module has input files. Run the module from the Case Modules tab to execute file analysis.",
            "input_files": [{"id": item.id, "filename": item.filename, "role": item.file_role} for item in module.files],
        }
    return {
        "status": "needs_input",
        "message": required.get(module.module_type, "Add module inputs before running analysis."),
        "summary": "Agent created the module and is waiting for user-provided experimental files or parameters.",
    }


async def _generate_artifact(
    mode: str,
    case_payload: dict[str, Any],
    goal: str,
    *,
    extra_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    provider = get_ai_provider()
    payload = dict(case_payload)
    if extra_context:
        payload["agent_context"] = extra_context
    payload["user_request"] = goal
    if mode == "troubleshooting":
        return await provider.generate_troubleshooting(payload.get("symptoms", []), payload)
    if mode == "report":
        return await provider.generate_report(payload)
    if mode == "rezonator":
        return await provider.generate_rezonator_schema(payload)
    return await provider.generate_plan({**payload, "goal": goal})
