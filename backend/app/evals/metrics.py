"""Metrics for RAG retrieval evaluations."""
from __future__ import annotations

from typing import Any


def contains_expected_title(result: dict[str, Any], expected: str | None) -> bool:
    if not expected:
        return False
    return expected.lower() in (result.get("title") or "").lower()


def contains_expected_terms(snippets: str, expected_terms: list[str]) -> bool:
    if not expected_terms:
        return False
    lower = snippets.lower()
    return all(term.lower() in lower for term in expected_terms)


def reciprocal_rank(results: list[dict[str, Any]], expected_source_ids: set[int], expected_title: str | None) -> float:
    for index, result in enumerate(results, start=1):
        source_match = bool(expected_source_ids and result.get("source_id") in expected_source_ids)
        title_match = contains_expected_title(result, expected_title)
        if source_match or title_match:
            return round(1.0 / index, 4)
    return 0.0


def evaluate_retrieval_row(row: dict[str, Any], results: list[dict[str, Any]], run) -> dict[str, Any]:
    source_ids = [int(item["source_id"]) for item in results]
    snippets = " ".join(item.get("snippet", "") for item in results)

    expected_source_ids = {int(item) for item in row.get("expected_source_ids") or []}
    expected_title = row.get("expected_source_title_contains")
    expected_terms = row.get("expected_terms") or []
    source_hit = bool(expected_source_ids and expected_source_ids & set(source_ids))
    title_hit = any(contains_expected_title(item, expected_title) for item in results)
    term_hit = contains_expected_terms(snippets, expected_terms)

    should_answer = bool(row.get("should_answer", True))
    predicted_answer = not bool(run.no_answer)
    if should_answer:
        hit = source_hit or title_hit or term_hit or (
            not expected_source_ids and not expected_title and not expected_terms and bool(results)
        )
    else:
        hit = not predicted_answer

    return {
        "id": row["id"],
        "query": row["query"],
        "case_id": row.get("case_id"),
        "should_answer": should_answer,
        "predicted_answer": predicted_answer,
        "hit": hit,
        "source_hit": source_hit,
        "title_hit": title_hit,
        "term_hit": term_hit,
        "mrr": reciprocal_rank(results, expected_source_ids, expected_title),
        "source_ids": source_ids,
        "expected_source_ids": sorted(expected_source_ids),
        "expected_source_title_contains": expected_title,
        "expected_terms": expected_terms,
        "max_score": round(float(run.max_score or 0.0), 4),
        "confidence": run.confidence,
        "no_answer": bool(run.no_answer),
    }


def summarize_eval_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    positives = [item for item in rows if item["should_answer"]]
    negatives = [item for item in rows if not item["should_answer"]]
    return {
        "total": total,
        "hit_rate": round(sum(1 for item in rows if item["hit"]) / total, 4) if total else 0.0,
        "positive_hit_rate": round(sum(1 for item in positives if item["hit"]) / len(positives), 4) if positives else 0.0,
        "negative_rejection_rate": round(sum(1 for item in negatives if item["hit"]) / len(negatives), 4) if negatives else 0.0,
        "mean_mrr": round(sum(float(item.get("mrr") or 0.0) for item in positives) / len(positives), 4) if positives else 0.0,
        "mean_max_score": round(sum(float(item.get("max_score") or 0.0) for item in rows) / total, 4) if total else 0.0,
    }


def evaluate_acceptance_thresholds(
    summary: dict[str, Any],
    *,
    min_positive_hit_rate: float | None = None,
    min_negative_rejection_rate: float | None = None,
    min_mean_mrr: float | None = None,
) -> dict[str, Any]:
    thresholds = {
        "min_positive_hit_rate": min_positive_hit_rate,
        "min_negative_rejection_rate": min_negative_rejection_rate,
        "min_mean_mrr": min_mean_mrr,
    }
    checks = [
        ("positive_hit_rate", "min_positive_hit_rate", min_positive_hit_rate),
        ("negative_rejection_rate", "min_negative_rejection_rate", min_negative_rejection_rate),
        ("mean_mrr", "min_mean_mrr", min_mean_mrr),
    ]
    failures = []
    for metric_key, threshold_key, threshold in checks:
        if threshold is None:
            continue
        actual = float(summary.get(metric_key) or 0.0)
        if actual < threshold:
            failures.append(
                {
                    "metric": metric_key,
                    "actual": round(actual, 4),
                    "threshold": threshold,
                    "threshold_key": threshold_key,
                }
            )
    return {
        "passed": not failures,
        "thresholds": {key: value for key, value in thresholds.items() if value is not None},
        "failures": failures,
    }
