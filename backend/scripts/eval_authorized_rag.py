from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.database import SessionLocal
from app.evals.datasets import load_jsonl_dataset
from app.evals.metrics import evaluate_acceptance_thresholds, evaluate_retrieval_row, summarize_eval_rows
from app.knowledge.retrieval import search_knowledge


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a RAG eval JSONL dataset against the configured database.")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output", default=None)
    parser.add_argument("--min-positive-hit-rate", type=float, default=None)
    parser.add_argument("--min-negative-rejection-rate", type=float, default=None)
    parser.add_argument("--min-mean-mrr", type=float, default=None)
    args = parser.parse_args()

    dataset = load_jsonl_dataset(args.dataset)
    rows = []
    db = SessionLocal()
    try:
        for row in dataset:
            run, results = search_knowledge(db, query=row["query"], case_id=row.get("case_id"), top_k=args.top_k)
            rows.append(evaluate_retrieval_row(row, [item.model_dump() for item in results], run))
            db.rollback()
    finally:
        db.close()

    summary = summarize_eval_rows(rows)
    acceptance = evaluate_acceptance_thresholds(
        summary,
        min_positive_hit_rate=args.min_positive_hit_rate,
        min_negative_rejection_rate=args.min_negative_rejection_rate,
        min_mean_mrr=args.min_mean_mrr,
    )
    report = {
        "dataset": args.dataset,
        "top_k": args.top_k,
        "summary": summary,
        "acceptance": acceptance,
        "rows": rows,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    if not acceptance["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
