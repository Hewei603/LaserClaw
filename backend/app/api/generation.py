"""Content generation API routes."""
from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from typing import Any, Awaitable

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth.acl import assert_case_edit, assert_case_view
from ..auth.security import Principal, get_current_principal
from ..agent.tools import get_case_payload, saved_project_physics
from ..database import get_db
from ..knowledge.ingestion import create_generated_content_source
from ..knowledge.retrieval import results_to_citations, search_case_and_global_knowledge
from ..inventory.evaluator import available_mirror_rocs
from ..models import ExperimentCase, GeneratedContent, PromptVersion
from ..observability.audit import record_audit
from ..observability.usage import apply_usage_to_generated
from ..physics.case_context import compute_case_physics
from ..providers import get_ai_provider
from ..schemas import GeneratedContentResponse, GenerateRequest

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_case_or_404(case_id: int, db: Session) -> ExperimentCase:
    case = db.query(ExperimentCase).filter(ExperimentCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Case {case_id} does not exist")
    return case


def _full_case_data(case: ExperimentCase, *, physics: dict[str, Any] | None = None) -> dict[str, Any]:
    data = get_case_payload(case)
    if physics is not None:
        # Deterministic kernel first: the model writes prose around these numbers
        # instead of inventing its own geometry.
        data["computed_physics"] = physics
    return data


def _query_for(case: ExperimentCase, content_type: str) -> str:
    symptoms = " ".join(case.symptoms or [])
    parameters = " ".join(f"{key} {value}" for key, value in (case.parameters or {}).items())
    return f"{content_type} {case.title} {case.cavity_type} {case.goal} {symptoms} {parameters}"


async def _run_generation(content_type: str, work: Awaitable[dict[str, Any]]) -> tuple[dict[str, Any], int]:
    started = perf_counter()
    try:
        return await work, int((perf_counter() - started) * 1000)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to generate %s content", content_type)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to generate {content_type}: {exc}",
        ) from exc


def _prepare_rag(case: ExperimentCase, content_type: str, case_data: dict[str, Any], request: GenerateRequest, db: Session) -> dict[str, Any]:
    """Retrieve once, BEFORE generation; save precisely the evidence sent in."""
    if not request.use_rag:
        return {}
    run, results = search_case_and_global_knowledge(
        db,
        query=_query_for(case, content_type),
        case_id=case.id,
        top_k=request.top_k,
    )
    retrieval = {
        "run_id": run.id,
        "max_score": round(run.max_score or 0.0, 4),
        "no_answer": bool(run.no_answer),
        "message": (run.filters_json or {}).get("low_confidence_message"),
    }
    metadata = {
        "citations": results_to_citations(results),
        "confidence": run.confidence or "low",
        "retrieval": retrieval,
    }
    case_data["retrieved_knowledge"] = [result.model_dump() for result in results]
    case_data["retrieval_context"] = metadata
    case_data["evidence_instructions"] = (
        "Use the retrieved evidence when relevant and cite its source title. "
        "Apply global lab rules before case-specific suggestions. "
        "If retrieval.no_answer is true, state that supporting evidence is insufficient; "
        "do not present a retrieved source as proof of an unsupported claim. "
        "Distinguish recorded measurements from hypotheses."
    )
    return metadata


def _attach_retrieval(content: dict[str, Any], metadata: dict[str, Any]) -> None:
    content.update(metadata)
    if metadata.get("retrieval", {}).get("no_answer"):
        missing = content.get("missing_information") or []
        if not isinstance(missing, list):
            missing = [missing]
        message = metadata["retrieval"]["message"] or "No matching evidence was found; review the source documents."
        content["missing_information"] = [*missing, message] if message not in missing else missing


def _save_generated_content(
    case_id: int,
    content_type: str,
    content: dict[str, Any],
    db: Session,
    *,
    latency_ms: int | None = None,
) -> GeneratedContent:
    prompt = (
        db.query(PromptVersion)
        .filter(PromptVersion.name == content_type, PromptVersion.is_active == True)  # noqa: E712
        .order_by(PromptVersion.created_at.desc())
        .first()
    )
    generated = GeneratedContent(
        case_id=case_id,
        content_type=content_type,
        content=content,
        prompt_version=f"{prompt.name}:{prompt.version}" if prompt else f"{content_type}_rag_v1",
        latency_ms=latency_ms,
    )
    apply_usage_to_generated(generated, content)
    db.add(generated)
    db.flush()
    create_generated_content_source(db, generated)
    record_audit(db, action="generation.create", resource_type="generated_content", resource_id=str(generated.id))
    db.commit()
    db.refresh(generated)
    return generated


@router.post("/{case_id}/generate-plan", response_model=GeneratedContentResponse)
async def generate_plan(
    case_id: int,
    request: GenerateRequest = GenerateRequest(),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Generate an experiment plan with retrieval citations."""
    case = _get_case_or_404(case_id, db)
    assert_case_edit(db, case, principal)
    provider = get_ai_provider()
    # The cavity search is unbounded, user-controlled CPU work: compute it ONCE
    # and off the event loop so one case cannot stall the whole server.
    case_data = _full_case_data(case)
    physics = saved_project_physics(case_data)
    if physics is None:
        rocs = available_mirror_rocs(db)
        physics = await asyncio.to_thread(compute_case_physics, case.parameters, available_rocs=rocs)
    case_data["computed_physics"] = physics
    retrieval = _prepare_rag(case, "plan", case_data, request, db)
    content, latency_ms = await _run_generation(
        "plan", provider.generate_plan(case_data)
    )
    content["computed_physics"] = physics
    _attach_retrieval(content, retrieval)
    return _save_generated_content(case_id, "plan", content, db, latency_ms=latency_ms)


@router.post("/{case_id}/generate-troubleshooting", response_model=GeneratedContentResponse)
async def generate_troubleshooting(
    case_id: int,
    request: GenerateRequest = GenerateRequest(),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Generate troubleshooting advice with retrieved context citations."""
    case = _get_case_or_404(case_id, db)
    assert_case_edit(db, case, principal)
    case_data = _full_case_data(case)
    retrieval = _prepare_rag(case, "troubleshooting", case_data, request, db)
    provider = get_ai_provider()
    content, latency_ms = await _run_generation("troubleshooting", provider.generate_troubleshooting(case.symptoms, case_data))
    _attach_retrieval(content, retrieval)
    return _save_generated_content(case_id, "troubleshooting", content, db, latency_ms=latency_ms)


@router.post("/{case_id}/generate-report", response_model=GeneratedContentResponse)
async def generate_report(
    case_id: int,
    request: GenerateRequest = GenerateRequest(),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Generate an experiment report."""
    case = _get_case_or_404(case_id, db)
    assert_case_edit(db, case, principal)
    provider = get_ai_provider()
    case_data = _full_case_data(case)
    retrieval = _prepare_rag(case, "report", case_data, request, db)
    content, latency_ms = await _run_generation("report", provider.generate_report(case_data))
    _attach_retrieval(content, retrieval)
    return _save_generated_content(case_id, "report", content, db, latency_ms=latency_ms)


@router.get("/{case_id}/generated-contents", response_model=list[GeneratedContentResponse])
async def list_generated_contents(
    case_id: int,
    content_type: str = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """List generated content for a case."""
    case = _get_case_or_404(case_id, db)
    assert_case_view(db, case, principal)
    query = db.query(GeneratedContent).filter(GeneratedContent.case_id == case_id)
    if content_type:
        query = query.filter(GeneratedContent.content_type == content_type)
    return query.order_by(GeneratedContent.generated_at.desc()).all()
