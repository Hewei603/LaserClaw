from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import get_settings
from app.database import SessionLocal
from app.evals.datasets import load_jsonl_dataset
from app.evals.metrics import evaluate_retrieval_row, summarize_eval_rows
from app.knowledge.retrieval import search_knowledge


def run_once(dataset: list[dict], *, min_score: float, low_score: float, top_k: int) -> dict:
    os.environ["RETRIEVAL_MIN_SCORE"] = str(min_score)
    os.environ["RETRIEVAL_LOW_CONFIDENCE_SCORE"] = str(low_score)
    get_settings.cache_clear()

    rows = []
    db = SessionLocal()
    try:
        for item in dataset:
            run, results = search_knowledge(db, query=item["query"], case_id=item.get("case_id"), top_k=top_k)
            rows.append(evaluate_retrieval_row(item, [result.model_dump() for result in results], run))
            db.rollback()
    finally:
        db.close()
    summary = summarize_eval_rows(rows)
    return {
        "min_score": min_score,
        "low_score": low_score,
        **summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan retrieval thresholds against an eval JSONL dataset.")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    dataset = load_jsonl_dataset(args.dataset)
    candidates = []
    for min_score in [0.04, 0.06, 0.08, 0.10, 0.12, 0.14]:
        for low_score in [0.10, 0.12, 0.14, 0.18, 0.22, 0.26]:
            if low_score < min_score:
                continue
            candidates.append(run_once(dataset, min_score=min_score, low_score=low_score, top_k=args.top_k))

    candidates.sort(
        key=lambda item: (
            item["hit_rate"],
            item["negative_rejection_rate"],
            item["positive_hit_rate"],
        ),
        reverse=True,
    )
    print(json.dumps(candidates[:20], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
