"""Agent tool registry and executable tools."""
from __future__ import annotations

from time import perf_counter
from typing import Any, Callable

from sqlalchemy.orm import Session

from ..knowledge.retrieval import results_to_citations, search_case_and_global_knowledge
from ..models import AgentTask, AgentToolCall, ExperimentCase, GeneratedContent


def tool_schemas() -> list[dict[str, Any]]:
    """Return public tool schemas for inspection and Agent prompting."""
    return [
        {"name": "get_case", "description": "Read an experiment case.", "input_schema": {"required": ["case_id"]}},
        {"name": "list_generated_contents", "description": "List prior generated artifacts.", "input_schema": {"required": ["case_id"]}},
        {"name": "list_attachments", "description": "List case attachments.", "input_schema": {"required": ["case_id"]}},
        {"name": "search_knowledge", "description": "Search indexed cases, attachments, and generated content.", "input_schema": {"required": ["query"]}},
        {"name": "search_similar_cases", "description": "Search case sources with similar symptoms and cavity type.", "input_schema": {"required": ["query"]}},
        {"name": "save_generated_content", "description": "Persist an Agent artifact.", "input_schema": {"required": ["case_id", "content_type", "content"]}},
    ]


def record_tool_call(
    db: Session,
    task: AgentTask,
    step_id: int | None,
    tool_name: str,
    input_json: dict[str, Any],
    runner: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    started = perf_counter()
    call = AgentToolCall(task_id=task.id, step_id=step_id, tool_name=tool_name, input_json=input_json)
    db.add(call)
    try:
        output = runner()
        call.output_json = output
        call.status = "completed"
        return output
    except Exception as exc:
        call.status = "failed"
        call.error_message = str(exc)
        raise
    finally:
        call.latency_ms = int((perf_counter() - started) * 1000)


def get_case_payload(case: ExperimentCase) -> dict[str, Any]:
    return {
        "id": case.id,
        "title": case.title,
        "description": case.description,
        "cavity_type": case.cavity_type,
        "goal": case.goal,
        "parameters": case.parameters or {},
        "symptoms": case.symptoms or [],
    }


def search_payload(db: Session, query: str, case_id: int | None, top_k: int, task_id: int | None) -> dict[str, Any]:
    run, results = search_case_and_global_knowledge(db, query=query, case_id=case_id, top_k=top_k, task_id=task_id)
    return {
        "retrieval_run_id": run.id,
        "confidence": run.confidence,
        "no_answer": bool(run.no_answer),
        "max_score": round(run.max_score or 0.0, 4),
        "message": (run.filters_json or {}).get("low_confidence_message"),
        "results": [result.model_dump() for result in results],
        "citations": results_to_citations(results),
    }


def list_generated_contents_payload(case: ExperimentCase) -> dict[str, Any]:
    return {
        "items": [
            {
                "id": item.id,
                "content_type": item.content_type,
                "generated_at": item.generated_at.isoformat() if item.generated_at else None,
            }
            for item in case.generated_contents
        ]
    }


def list_attachments_payload(case: ExperimentCase) -> dict[str, Any]:
    return {
        "items": [
            {
                "id": attachment.id,
                "filename": attachment.filename,
                "file_type": attachment.file_type,
            }
            for attachment in case.attachments
        ]
    }


def save_generated_content_payload(generated: GeneratedContent) -> dict[str, Any]:
    return {"generated_content_id": generated.id, "content_type": generated.content_type}
