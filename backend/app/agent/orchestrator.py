"""Stateful Agent orchestrator."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..knowledge.ingestion import create_generated_content_source
from ..models import AgentStep, AgentTask, ExperimentCase, GeneratedContent
from ..observability.audit import record_audit
from ..providers import get_ai_provider
from .guardrails import assess_risk
from .planner import build_plan
from .tools import (
    get_case_payload,
    list_attachments_payload,
    list_generated_contents_payload,
    record_tool_call,
    save_generated_content_payload,
    search_payload,
)

logger = logging.getLogger(__name__)


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
        task.status = "failed"
        for step in steps:
            if step.status == "pending":
                step.status = "failed"
                break
        record_audit(db, action="agent_task.failed", resource_type="agent_task", resource_id=str(task.id))
        db.commit()
        raise


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
