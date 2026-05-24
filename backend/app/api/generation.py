"""Content generation API routes."""
from __future__ import annotations

import logging
from time import perf_counter
from typing import Any, Awaitable

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..knowledge.ingestion import create_generated_content_source
from ..knowledge.retrieval import results_to_citations, search_case_and_global_knowledge
from ..models import ExperimentCase, GeneratedContent, PromptVersion
from ..observability.audit import record_audit
from ..observability.usage import apply_usage_to_generated
from ..providers import get_ai_provider
from ..schemas import GeneratedContentResponse, GenerateRequest

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_case_or_404(case_id: int, db: Session) -> ExperimentCase:
    case = db.query(ExperimentCase).filter(ExperimentCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Case {case_id} does not exist")
    return case


def _full_case_data(case: ExperimentCase) -> dict[str, Any]:
    return {
        "title": case.title,
        "description": case.description,
        "cavity_type": case.cavity_type,
        "goal": case.goal,
        "parameters": case.parameters,
        "symptoms": case.symptoms,
    }


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


def _augment_with_rag(case: ExperimentCase, content_type: str, content: dict[str, Any], request: GenerateRequest, db: Session) -> None:
    if not request.use_rag:
        return
    run, results = search_case_and_global_knowledge(
        db,
        query=_query_for(case, content_type),
        case_id=case.id,
        top_k=request.top_k,
    )
    content["citations"] = results_to_citations(results)
    content["confidence"] = run.confidence or ("medium" if results else "low")
    content["retrieval"] = {
        "run_id": run.id,
        "max_score": round(run.max_score or 0.0, 4),
        "no_answer": bool(run.no_answer),
        "message": (run.filters_json or {}).get("low_confidence_message"),
    }
    if run.no_answer:
        content["missing_information"] = [
            (run.filters_json or {}).get("low_confidence_message")
            or "No matching knowledge source was found; review attachments and case history."
        ]


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
async def generate_plan(case_id: int, request: GenerateRequest = GenerateRequest(), db: Session = Depends(get_db)):
    """Generate an experiment plan with retrieval citations."""
    case = _get_case_or_404(case_id, db)
    provider = get_ai_provider()
    content, latency_ms = await _run_generation("plan", provider.generate_plan(_full_case_data(case)))
    _augment_with_rag(case, "plan", content, request, db)
    return _save_generated_content(case_id, "plan", content, db, latency_ms=latency_ms)


@router.post("/{case_id}/generate-rezonator", response_model=GeneratedContentResponse)
async def generate_rezonator(case_id: int, request: GenerateRequest = GenerateRequest(), db: Session = Depends(get_db)):
    """Generate a ReZonator schema draft."""
    case = _get_case_or_404(case_id, db)
    case_data = {"title": case.title, "cavity_type": case.cavity_type, "parameters": case.parameters}
    provider = get_ai_provider()
    content, latency_ms = await _run_generation("rezonator", provider.generate_rezonator_schema(case_data))
    _augment_with_rag(case, "rezonator", content, request, db)
    return _save_generated_content(case_id, "rezonator", content, db, latency_ms=latency_ms)


@router.post("/{case_id}/generate-troubleshooting", response_model=GeneratedContentResponse)
async def generate_troubleshooting(case_id: int, request: GenerateRequest = GenerateRequest(), db: Session = Depends(get_db)):
    """Generate troubleshooting advice with retrieved context citations."""
    case = _get_case_or_404(case_id, db)
    case_data = {"title": case.title, "cavity_type": case.cavity_type, "parameters": case.parameters}
    provider = get_ai_provider()
    content, latency_ms = await _run_generation("troubleshooting", provider.generate_troubleshooting(case.symptoms, case_data))
    _augment_with_rag(case, "troubleshooting", content, request, db)
    return _save_generated_content(case_id, "troubleshooting", content, db, latency_ms=latency_ms)


@router.post("/{case_id}/generate-report", response_model=GeneratedContentResponse)
async def generate_report(case_id: int, request: GenerateRequest = GenerateRequest(), db: Session = Depends(get_db)):
    """Generate an experiment report."""
    case = _get_case_or_404(case_id, db)
    provider = get_ai_provider()
    content, latency_ms = await _run_generation("report", provider.generate_report(_full_case_data(case)))
    _augment_with_rag(case, "report", content, request, db)
    return _save_generated_content(case_id, "report", content, db, latency_ms=latency_ms)


@router.get("/{case_id}/generated-contents", response_model=list[GeneratedContentResponse])
async def list_generated_contents(case_id: int, content_type: str = None, db: Session = Depends(get_db)):
    """List generated content for a case."""
    query = db.query(GeneratedContent).filter(GeneratedContent.case_id == case_id)
    if content_type:
        query = query.filter(GeneratedContent.content_type == content_type)
    return query.order_by(GeneratedContent.generated_at.desc()).all()
