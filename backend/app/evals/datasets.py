"""Dataset loading for private or synthetic RAG evaluations."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _require_type(row: dict[str, Any], key: str, expected_type: type | tuple[type, ...], line_no: int) -> None:
    if key in row and not isinstance(row[key], expected_type):
        raise ValueError(f"Dataset row {line_no} field {key} has invalid type")


def _validate_string_list(row: dict[str, Any], key: str, line_no: int) -> None:
    if key not in row:
        return
    value = row[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"Dataset row {line_no} field {key} must be a list of strings")


def _validate_int_list(row: dict[str, Any], key: str, line_no: int) -> None:
    if key not in row:
        return
    value = row[key]
    if not isinstance(value, list) or not all(isinstance(item, int) for item in value):
        raise ValueError(f"Dataset row {line_no} field {key} must be a list of integers")


def validate_eval_row(row: dict[str, Any], line_no: int) -> dict[str, Any]:
    if "id" not in row or "query" not in row:
        raise ValueError(f"Dataset row {line_no} must include id and query")
    _require_type(row, "id", str, line_no)
    _require_type(row, "query", str, line_no)
    _require_type(row, "should_answer", bool, line_no)
    _require_type(row, "case_id", int, line_no)
    _require_type(row, "expected_source_title_contains", str, line_no)
    _validate_int_list(row, "expected_source_ids", line_no)
    _validate_string_list(row, "expected_terms", line_no)
    row.setdefault("should_answer", True)
    row.setdefault("expected_source_ids", [])
    row.setdefault("expected_terms", [])
    return row


def load_jsonl_dataset(path: str | Path) -> list[dict[str, Any]]:
    """Load a JSONL eval dataset.

    Each row must include `id` and `query`. Rows may include:
    `case_id`, `should_answer`, `expected_source_ids`,
    `expected_source_title_contains`, and `expected_terms`.
    """
    dataset_path = Path(path)
    rows: list[dict[str, Any]] = []
    for line_no, raw_line in enumerate(dataset_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at line {line_no}: {exc}") from exc
        rows.append(validate_eval_row(row, line_no))
    return rows
