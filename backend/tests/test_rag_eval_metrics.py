import json
from pathlib import Path

import pytest

from app.evals.datasets import load_jsonl_dataset
from app.evals.metrics import evaluate_acceptance_thresholds, evaluate_retrieval_row, summarize_eval_rows


class _Run:
    no_answer = True
    max_score = 0.02
    confidence = "low"


def test_jsonl_dataset_loader_defaults(tmp_path):
    path = tmp_path / "dataset.jsonl"
    path.write_text(json.dumps({"id": "neg-1", "query": "coffee policy"}) + "\n", encoding="utf-8")

    rows = load_jsonl_dataset(path)

    assert rows == [
        {
            "id": "neg-1",
            "query": "coffee policy",
            "should_answer": True,
            "expected_source_ids": [],
            "expected_terms": [],
        }
    ]


def test_jsonl_dataset_loader_rejects_missing_query(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text(json.dumps({"id": "bad"}) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must include id and query"):
        load_jsonl_dataset(path)


def test_jsonl_dataset_loader_rejects_invalid_field_types(tmp_path):
    path = tmp_path / "bad-types.jsonl"
    path.write_text(
        json.dumps({"id": "bad", "query": "coffee policy", "expected_terms": "coffee"}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="expected_terms must be a list of strings"):
        load_jsonl_dataset(path)


def test_negative_eval_row_counts_no_answer_as_hit():
    row = {"id": "neg-1", "query": "unrelated coffee policy", "should_answer": False}

    result = evaluate_retrieval_row(row, [], _Run())

    assert result["hit"] is True
    assert result["predicted_answer"] is False
    summary = summarize_eval_rows([result])
    assert summary["negative_rejection_rate"] == 1.0


def test_eval_acceptance_thresholds_report_failures():
    summary = {
        "positive_hit_rate": 0.8,
        "negative_rejection_rate": 0.95,
        "mean_mrr": 0.7,
    }

    result = evaluate_acceptance_thresholds(
        summary,
        min_positive_hit_rate=0.85,
        min_negative_rejection_rate=0.9,
        min_mean_mrr=0.75,
    )

    assert result["passed"] is False
    assert [failure["metric"] for failure in result["failures"]] == ["positive_hit_rate", "mean_mrr"]


def test_inline_rag_eval_records_summary_and_negative_rows(client):
    response = client.post(
        "/api/evals/rag",
        json={
            "name": "negative smoke",
            "dataset": [
                {
                    "id": "neg-1",
                    "query": "unrelated coffee machine warranty policy",
                    "should_answer": False,
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_questions"] == 1
    assert payload["results"]["summary"]["negative_rejection_rate"] == 1.0
    assert payload["results"]["rows"][0]["should_answer"] is False


def test_private_rag_eval_requires_allowed_path(client):
    forbidden = client.post(
        "/api/evals/rag/private-dataset",
        params={"dataset_path": str(Path("outside.jsonl")), "top_k": 5},
        headers={"x-user-role": "reviewer", "x-user-id": "2"},
    )

    assert forbidden.status_code == 400


def test_private_rag_eval_rejects_prefix_sibling_path(client, tmp_path):
    sibling = tmp_path / "private-sibling.jsonl"
    sibling.write_text(json.dumps({"id": "neg-1", "query": "coffee", "should_answer": False}) + "\n", encoding="utf-8")

    response = client.post(
        "/api/evals/rag/private-dataset",
        params={"dataset_path": str(sibling), "top_k": 5},
        headers={"x-user-role": "reviewer", "x-user-id": "2"},
    )

    assert response.status_code == 400


def test_private_rag_eval_runs_jsonl_from_allowed_root(client):
    root = Path(__file__).resolve().parents[2] / "docs" / "evals" / "private"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "test_private_eval_runtime.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "neg-1",
                "query": "unrelated coffee machine warranty policy",
                "should_answer": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    try:
        response = client.post(
            "/api/evals/rag/private-dataset",
            params={"dataset_path": str(path), "top_k": 5},
            headers={"x-user-role": "reviewer", "x-user-id": "2"},
        )
    finally:
        path.unlink(missing_ok=True)

    assert response.status_code == 200
    assert response.json()["name"] == "private:test_private_eval_runtime.jsonl"
    assert response.json()["results"]["summary"]["negative_rejection_rate"] == 1.0
