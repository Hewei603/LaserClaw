"""RAG evaluation and benchmark API."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth.security import Principal, get_current_principal
from ..database import get_db
from ..knowledge.retrieval import search_knowledge
from ..models import RagEvalRun
from ..observability.audit import record_audit
from ..schemas import RagEvalRequest, RagEvalRunResponse

router = APIRouter()


@router.post("/rag", response_model=RagEvalRunResponse)
async def run_rag_eval(
    payload: RagEvalRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Run a lightweight retrieval benchmark against an inline dataset."""
    rows: list[dict] = []
    hits = 0
    max_scores: list[float] = []
    for item in payload.dataset:
        run, results = search_knowledge(db, query=item.query, case_id=item.case_id, top_k=payload.top_k)
        source_ids = [result.source_id for result in results]
        snippets = " ".join(result.snippet.lower() for result in results)
        source_hit = bool(item.expected_source_ids and set(item.expected_source_ids) & set(source_ids))
        term_hit = bool(item.expected_terms and all(term.lower() in snippets for term in item.expected_terms))
        hit = source_hit or term_hit or (not item.expected_source_ids and not item.expected_terms and bool(results))
        hits += 1 if hit else 0
        max_score = float(run.max_score or 0.0)
        max_scores.append(max_score)
        rows.append(
            {
                "query": item.query,
                "case_id": item.case_id,
                "retrieval_run_id": run.id,
                "hit": hit,
                "source_ids": source_ids,
                "expected_source_ids": item.expected_source_ids,
                "expected_terms": item.expected_terms,
                "max_score": round(max_score, 4),
                "confidence": run.confidence,
                "no_answer": bool(run.no_answer),
            }
        )
    total = len(payload.dataset)
    eval_run = RagEvalRun(
        name=payload.name,
        dataset=[item.model_dump() for item in payload.dataset],
        results=rows,
        total_questions=total,
        hit_rate=round(hits / total, 4) if total else 0.0,
        mean_max_score=round(sum(max_scores) / total, 4) if total else 0.0,
        created_by_id=principal.user_id,
    )
    db.add(eval_run)
    db.flush()
    record_audit(db, action="rag_eval.run", resource_type="rag_eval_run", resource_id=str(eval_run.id))
    db.commit()
    db.refresh(eval_run)
    return eval_run


@router.get("/rag", response_model=list[RagEvalRunResponse])
async def list_rag_evals(limit: int = 50, db: Session = Depends(get_db)):
    return db.query(RagEvalRun).order_by(RagEvalRun.created_at.desc()).limit(limit).all()
