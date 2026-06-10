"""RAG evaluation and benchmark API."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth.acl import can_manage_knowledge
from ..auth.security import Principal, get_current_principal
from ..database import get_db
from ..evals.datasets import load_jsonl_dataset
from ..evals.metrics import evaluate_retrieval_row, summarize_eval_rows
from ..knowledge.retrieval import search_knowledge
from ..models import RagEvalRun
from ..observability.audit import record_audit
from ..schemas import RagEvalRequest, RagEvalRunResponse

router = APIRouter()
REPO_ROOT = Path(__file__).resolve().parents[3]
PRIVATE_EVAL_ROOT = REPO_ROOT / "docs" / "evals" / "private"


def _run_dataset(
    db: Session,
    *,
    name: str,
    dataset: list[dict],
    top_k: int,
    principal: Principal,
) -> RagEvalRun:
    rows: list[dict] = []
    for index, item in enumerate(dataset, start=1):
        item = {**item, "id": item.get("id") or f"row-{index}"}
        run, results = search_knowledge(db, query=item["query"], case_id=item.get("case_id"), top_k=top_k)
        row = evaluate_retrieval_row(item, [result.model_dump() for result in results], run)
        row["retrieval_run_id"] = run.id
        rows.append(row)

    summary = summarize_eval_rows(rows)
    eval_run = RagEvalRun(
        name=name,
        dataset=dataset,
        results={
            "summary": summary,
            "rows": rows,
        },
        total_questions=summary["total"],
        hit_rate=summary["hit_rate"],
        mean_max_score=summary["mean_max_score"],
        created_by_id=principal.user_id,
    )
    db.add(eval_run)
    db.flush()
    return eval_run


@router.post("/rag", response_model=RagEvalRunResponse)
async def run_rag_eval(
    payload: RagEvalRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Run a lightweight retrieval benchmark against an inline dataset."""
    eval_run = _run_dataset(
        db,
        name=payload.name,
        dataset=[item.model_dump() for item in payload.dataset],
        top_k=payload.top_k,
        principal=principal,
    )
    record_audit(db, action="rag_eval.run", resource_type="rag_eval_run", resource_id=str(eval_run.id))
    db.commit()
    db.refresh(eval_run)
    return eval_run


@router.post("/rag/private-dataset", response_model=RagEvalRunResponse)
async def run_private_rag_eval(
    dataset_path: str,
    top_k: int = 5,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Run an eval dataset stored under docs/evals/private."""
    if not can_manage_knowledge(principal):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin or reviewer role required")
    path = Path(dataset_path).resolve()
    allowed_root = PRIVATE_EVAL_ROOT.resolve()
    try:
        path.relative_to(allowed_root)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dataset path is not allowed")
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset file does not exist")
    dataset = load_jsonl_dataset(path)
    eval_run = _run_dataset(
        db,
        name=f"private:{path.name}",
        dataset=dataset,
        top_k=top_k,
        principal=principal,
    )
    record_audit(db, action="rag_eval.private_dataset.run", resource_type="rag_eval_run", resource_id=str(eval_run.id))
    db.commit()
    db.refresh(eval_run)
    return eval_run


@router.get("/rag", response_model=list[RagEvalRunResponse])
async def list_rag_evals(limit: int = 50, db: Session = Depends(get_db)):
    return db.query(RagEvalRun).order_by(RagEvalRun.created_at.desc()).limit(limit).all()
