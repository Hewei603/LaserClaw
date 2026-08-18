"""Standalone literature search endpoint.

Backs the 文献检索 page: a quick lookup without creating a case first. The
case-module and agent paths reuse the same service, so all three entries give
identical results for identical inputs.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..auth.security import Principal, get_current_principal
from ..literature import run_literature_search

router = APIRouter()


class LiteratureSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    year_from: int | None = None
    max_results: int | None = None
    sort: str = Field(default="relevance", pattern="^(relevance|citations|year)$")
    sources: str | None = None  # csv override; None = settings default


@router.post("/search")
async def search_literature(
    payload: LiteratureSearchRequest,
    principal: Principal = Depends(get_current_principal),
):
    """Search the configured sources; no case, nothing persisted."""
    _ = principal  # every /api route carries a principal (ACL audit invariant)
    config = payload.model_dump(exclude_none=True)
    # Off the event loop: this is a network call with an ~8s worst case.
    return await asyncio.to_thread(run_literature_search, config)
