"""Token and cost accounting helpers."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from ..models import GeneratedContent


# USD per 1M tokens. Keep conservative defaults and allow unknown models to
# record token usage without claiming a cost.
MODEL_PRICES: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
    "gpt-4o": (Decimal("2.50"), Decimal("10.00")),
    "gpt-5": (Decimal("1.25"), Decimal("10.00")),
    "gpt-5-mini": (Decimal("0.25"), Decimal("2.00")),
    "claude-sonnet-4-5": (Decimal("3.00"), Decimal("15.00")),
    "claude-3-5-sonnet": (Decimal("3.00"), Decimal("15.00")),
}


def estimate_cost_usd(model: str | None, input_tokens: int | None, output_tokens: int | None) -> str | None:
    if not model:
        return None
    prices = MODEL_PRICES.get(model.lower()) or MODEL_PRICES.get(model)
    if not prices:
        return None
    input_rate, output_rate = prices
    cost = (Decimal(input_tokens or 0) * input_rate + Decimal(output_tokens or 0) * output_rate) / Decimal(1_000_000)
    return f"{cost:.6f}"


def attach_usage_payload(content: dict[str, Any], *, provider: str, model: str, usage: dict[str, Any] | None) -> dict[str, Any]:
    usage = usage or {}
    input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens")
    output_tokens = usage.get("output_tokens") or usage.get("completion_tokens")
    cost = estimate_cost_usd(model, input_tokens, output_tokens)
    content["_usage"] = {
        "provider": provider,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": usage.get("total_tokens") or ((input_tokens or 0) + (output_tokens or 0)),
        "cost_estimate_usd": cost,
    }
    return content


def apply_usage_to_generated(generated: GeneratedContent, content: dict[str, Any]) -> None:
    usage = content.pop("_usage", None) or {}
    model = usage.get("model") or content.get("model")
    generated.model = model
    generated.input_tokens = usage.get("input_tokens")
    generated.output_tokens = usage.get("output_tokens")
    generated.cost_estimate = usage.get("cost_estimate_usd")


def monthly_usage_summary(db: Session, *, year: int | None = None, month: int | None = None) -> dict[str, Any]:
    query = db.query(GeneratedContent)
    if year is not None:
        query = query.filter(extract("year", GeneratedContent.generated_at) == year)
    if month is not None:
        query = query.filter(extract("month", GeneratedContent.generated_at) == month)

    rows = query.all()
    cost_total = Decimal("0")
    by_model: dict[str, dict[str, Any]] = {}
    for item in rows:
        model = item.model or "unknown"
        bucket = by_model.setdefault(
            model,
            {"model": model, "requests": 0, "input_tokens": 0, "output_tokens": 0, "cost_estimate_usd": "0.000000"},
        )
        bucket["requests"] += 1
        bucket["input_tokens"] += item.input_tokens or 0
        bucket["output_tokens"] += item.output_tokens or 0
        if item.cost_estimate:
            cost_total += Decimal(item.cost_estimate)
            bucket_cost = Decimal(bucket["cost_estimate_usd"]) + Decimal(item.cost_estimate)
            bucket["cost_estimate_usd"] = f"{bucket_cost:.6f}"

    totals = db.query(
        func.count(GeneratedContent.id),
        func.coalesce(func.sum(GeneratedContent.input_tokens), 0),
        func.coalesce(func.sum(GeneratedContent.output_tokens), 0),
    )
    if year is not None:
        totals = totals.filter(extract("year", GeneratedContent.generated_at) == year)
    if month is not None:
        totals = totals.filter(extract("month", GeneratedContent.generated_at) == month)
    request_count, input_tokens, output_tokens = totals.one()

    return {
        "year": year,
        "month": month,
        "requests": request_count,
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "cost_estimate_usd": f"{cost_total:.6f}",
        "by_model": sorted(by_model.values(), key=lambda item: item["requests"], reverse=True),
    }
