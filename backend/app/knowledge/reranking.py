"""Two-stage reranking for RAG retrieval.

The first retrieval stage uses vector/lexical scoring for recall.
This module implements the second stage: reranking a smaller candidate set
using a cross-encoder for higher-precision ordering.
"""
from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from ..config import get_settings

if TYPE_CHECKING:
    from ..models import KnowledgeChunk


@lru_cache(maxsize=2)
def _load_cross_encoder(model_name: str):
    try:
        from sentence_transformers import CrossEncoder
    except ImportError as exc:
        raise RuntimeError(
            "RERANKER_PROVIDER=sentence_transformers requires sentence-transformers. "
            "Install it: pip install sentence-transformers"
        ) from exc
    return CrossEncoder(model_name)


def rerank_chunks(
    query: str,
    scored_chunks: list[tuple[float, "KnowledgeChunk"]],
    *,
    top_k: int,
) -> list[tuple[float, "KnowledgeChunk"]]:
    """Rerank candidate chunks using the configured reranker.

    When reranker_provider is 'none', returns the top_k candidates unchanged.
    The final score is a weighted blend of the first-stage score and the
    cross-encoder score so that retrieval signal is not discarded entirely.
    """
    settings = get_settings()
    provider = settings.reranker_provider.lower()

    if provider == "none" or not scored_chunks:
        return scored_chunks[:top_k]

    if provider in {"sentence_transformers", "sentence-transformers"}:
        model = _load_cross_encoder(settings.reranker_model)
        pairs = [(query, chunk.text[:2000]) for _, chunk in scored_chunks]
        rerank_scores = model.predict(pairs)
        merged: list[tuple[float, KnowledgeChunk]] = []
        for (base_score, chunk), rerank_score in zip(scored_chunks, rerank_scores):
            final_score = (
                (1.0 - settings.reranker_weight) * float(base_score)
                + settings.reranker_weight * float(rerank_score)
            )
            merged.append((final_score, chunk))
        merged.sort(key=lambda item: item[0], reverse=True)
        return merged[:top_k]

    raise RuntimeError(f"Unsupported reranker provider: {settings.reranker_provider!r}")
