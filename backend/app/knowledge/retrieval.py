"""Knowledge retrieval services."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..config import get_settings
from sqlalchemy import or_

from ..models import KnowledgeChunk, KnowledgeSource, RetrievalResult, RetrievalRun
from ..schemas import Citation, KnowledgeSearchResult
from .embeddings import cosine_similarity, embed_text, lexical_similarity, tokenize
from .reranking import rerank_chunks
from .vector_store import chunks_by_ids, query_chunk_ids


SAFETY_TERMS = {
    "安全", "防护", "眼镜", "护目镜", "od", "ppe", "class", "联锁", "急停", "e-stop",
    "lso", "应急", "事故", "报告", "培训", "火灾", "触电", "皮肤", "眼睛", "准直",
    "调光", "开机", "关机", "钥匙", "控制区", "sop", "故障", "报警",
}
OPTICS_TERMS = {
    "器件", "透镜", "镜", "分束", "波片", "滤光", "晶体", "lbo", "ktp", "bbo",
    "nd:yag", "1064", "532", "808", "探测器", "功率计", "光谱仪", "光斑相机",
    "准直器", "光纤", "beam", "mirror", "lens", "crystal", "rezonator",
}


def _source_family(source: KnowledgeSource) -> str:
    title = (source.title or "").lower()
    if "safety" in title or "saf" in title or "安全" in title:
        return "safety"
    if "optic" in title or "component" in title or "器件" in title or "catalog" in title:
        return "optics"
    return "other"


def _domain_boost(query: str, source: KnowledgeSource, chunk: KnowledgeChunk) -> float:
    tokens = set(tokenize(query))
    text = f"{source.title} {chunk.text}".lower()
    family = _source_family(source)
    boost = 1.0

    safety_signal = bool(tokens & SAFETY_TERMS) or any(term in query.lower() for term in ["class 3", "class 4", "od", "e-stop"])
    optics_signal = bool(tokens & OPTICS_TERMS)

    if family == "safety" and safety_signal:
        boost += 0.35
    if family == "optics" and optics_signal:
        boost += 0.18
    if family == "optics" and safety_signal and not optics_signal:
        boost -= 0.18
    if family == "safety" and optics_signal and not safety_signal:
        boost -= 0.10

    for code in ["saf-", "opt-", "mir-", "cry-", "lns-", "det-", "flt-", "mnt-", "wvp-", "bs-"]:
        if code in query.lower() and code in text:
            boost += 0.25
    return max(boost, 0.2)


def _combined_score(query: str, query_embedding: dict, chunk: KnowledgeChunk) -> float:
    settings = get_settings()
    vector_score = cosine_similarity(query_embedding, chunk.embedding or {})
    lexical_score = lexical_similarity(query, f"{chunk.source.title} {chunk.text}")
    weighted = (settings.retrieval_vector_weight * vector_score) + (settings.retrieval_lexical_weight * lexical_score)
    return weighted * _domain_boost(query, chunk.source, chunk)


def _sql_score_chunks(query: str, query_embedding: dict, chunk_query) -> list[tuple[float, KnowledgeChunk]]:
    scored: list[tuple[float, KnowledgeChunk]] = []
    for chunk in chunk_query.all():
        score = _combined_score(query, query_embedding, chunk)
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored


def _vector_store_score_chunks(
    db: Session,
    *,
    query: str,
    query_embedding: dict,
    top_k: int,
    case_id: int | None = None,
    source_type: str | None = None,
) -> list[tuple[float, KnowledgeChunk]]:
    scored_ids = query_chunk_ids(
        db,
        query_embedding=query_embedding,
        top_k=max(top_k * 4, top_k),
        case_id=case_id,
        source_type=source_type,
    )
    scored = []
    for vector_score, chunk in chunks_by_ids(db, scored_ids):
        lexical_score = lexical_similarity(query, f"{chunk.source.title} {chunk.text}")
        settings = get_settings()
        score = (
            settings.retrieval_vector_weight * vector_score
            + settings.retrieval_lexical_weight * lexical_score
        ) * _domain_boost(query, chunk.source, chunk)
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[:top_k]


def _confidence(selected: list[tuple[float, KnowledgeChunk]]) -> tuple[str, bool, str | None]:
    settings = get_settings()
    result_count = len(selected)
    max_score = selected[0][0] if selected else 0.0
    second_score = selected[1][0] if len(selected) > 1 else 0.0
    margin = max_score - second_score
    if result_count < settings.retrieval_min_results or max_score < settings.retrieval_min_score:
        return (
            "low",
            True,
            "The knowledge base does not contain enough evidence for this question. Review the source documents manually.",
        )
    if (
        settings.retrieval_negative_policy == "score_and_margin"
        and max_score < 0.28
        and margin < settings.retrieval_answer_margin_min
    ):
        return (
            "low",
            True,
            "Retrieved evidence is weak and ambiguous. Inspect the source documents before answering.",
        )
    if max_score < settings.retrieval_low_confidence_score:
        return (
            "low",
            True,
            "Retrieved evidence is weak. Treat the answer as uncertain and inspect the cited documents.",
        )
    if max_score < 0.28:
        return "medium", False, None
    return "high", False, None


def _new_retrieval_run(
    db: Session,
    *,
    task_id: int | None,
    query: str,
    filters: dict[str, object],
    top_k: int,
    selected: list[tuple[float, KnowledgeChunk]],
) -> RetrievalRun:
    max_score = selected[0][0] if selected else 0.0
    confidence, no_answer, message = _confidence(selected)
    run = RetrievalRun(
        task_id=task_id,
        query=query,
        filters_json={**filters, "low_confidence_message": message},
        top_k=top_k,
        max_score=max_score,
        confidence=confidence,
        no_answer=no_answer,
    )
    db.add(run)
    db.flush()
    return run


def search_knowledge(
    db: Session,
    *,
    query: str,
    case_id: int | None = None,
    source_type: str | None = None,
    top_k: int = 5,
    task_id: int | None = None,
    allowed_case_ids: list[int] | None = None,
) -> tuple[RetrievalRun, list[KnowledgeSearchResult]]:
    """Search knowledge chunks and persist a retrieval audit record."""
    query_embedding = embed_text(query)
    active_source_filter = or_(KnowledgeSource.governance_status.is_(None), KnowledgeSource.governance_status != "archived")
    chunk_query = db.query(KnowledgeChunk).join(KnowledgeSource).filter(active_source_filter)
    filters: dict[str, object] = {}
    if allowed_case_ids is not None and case_id is None:
        chunk_query = chunk_query.filter(or_(KnowledgeSource.case_id.is_(None), KnowledgeSource.case_id.in_(allowed_case_ids)))
        filters["allowed_case_ids"] = allowed_case_ids
    if allowed_case_ids is not None and case_id is not None and case_id not in allowed_case_ids:
        chunk_query = chunk_query.filter(KnowledgeSource.case_id == -1)
        filters["allowed_case_ids"] = allowed_case_ids
    if case_id is not None:
        chunk_query = chunk_query.filter(KnowledgeSource.case_id == case_id)
        filters["case_id"] = case_id
    if source_type:
        chunk_query = chunk_query.filter(KnowledgeSource.source_type == source_type)
        filters["source_type"] = source_type

    scored = _vector_store_score_chunks(
        db,
        query=query,
        query_embedding=query_embedding,
        top_k=top_k,
        case_id=case_id,
        source_type=source_type,
    )
    if allowed_case_ids is not None:
        scored = [
            (score, chunk)
            for score, chunk in scored
            if chunk.source.case_id is None or chunk.source.case_id in allowed_case_ids
        ]
    if not scored:
        scored = _sql_score_chunks(query, query_embedding, chunk_query)

    settings = get_settings()
    candidate_k = max(top_k * 4, settings.reranker_top_k)
    selected = rerank_chunks(query, scored[:candidate_k], top_k=top_k)

    run = _new_retrieval_run(db, task_id=task_id, query=query, filters=filters, top_k=top_k, selected=selected)

    results: list[KnowledgeSearchResult] = []
    for rank, (score, chunk) in enumerate(selected, start=1):
        db.add(RetrievalResult(retrieval_run_id=run.id, chunk_id=chunk.id, score=score, rank=rank))
        source = chunk.source
        results.append(
            KnowledgeSearchResult(
                source_id=source.id,
                chunk_id=chunk.id,
                title=source.title,
                source_type=source.source_type,
                score=round(score, 4),
                rank=rank,
                snippet=chunk.text[:500],
                metadata_json={**(source.metadata_json or {}), **(chunk.metadata_json or {})},
            )
        )
    return run, results


def results_to_citations(results: list[KnowledgeSearchResult]) -> list[dict]:
    return [
        Citation(
            source_id=result.source_id,
            chunk_id=result.chunk_id,
            title=result.title,
            source_type=result.source_type,
            score=result.score,
            snippet=result.snippet,
        ).model_dump()
        for result in results
    ]


def search_case_and_global_knowledge(
    db: Session,
    *,
    query: str,
    case_id: int | None = None,
    top_k: int = 8,
    task_id: int | None = None,
    global_slots: int = 5,
    case_slots: int = 3,
    allowed_case_ids: list[int] | None = None,
) -> tuple[RetrievalRun, list[KnowledgeSearchResult]]:
    """Two-tier retrieval: global lab docs always fill first N slots (the 'constitution'),
    then case-specific attachments fill the remaining slots.

    This guarantees lab-wide SOPs, safety rules, and equipment catalogs are always
    present in context regardless of how relevant the case attachments are.
    """
    query_embedding = embed_text(query)

    def _score_chunks(chunk_query) -> list[tuple[float, KnowledgeChunk]]:
        return _sql_score_chunks(query, query_embedding, chunk_query)

    # --- Tier 1: global lab documents (always retrieved) ---
    active_source_filter = or_(KnowledgeSource.governance_status.is_(None), KnowledgeSource.governance_status != "archived")
    global_query = (
        db.query(KnowledgeChunk)
        .join(KnowledgeSource)
        .filter(KnowledgeSource.case_id.is_(None), active_source_filter)
    )
    global_scored = _vector_store_score_chunks(
        db,
        query=query,
        query_embedding=query_embedding,
        top_k=global_slots,
        case_id=0,
    )
    if not global_scored:
        global_scored = _score_chunks(global_query)
    global_scored = rerank_chunks(query, global_scored[:max(global_slots * 4, get_settings().reranker_top_k)], top_k=global_slots)

    # --- Tier 2: case-specific attachments (only when a case is linked) ---
    case_scored: list[tuple[float, KnowledgeChunk]] = []
    if case_id is not None and (allowed_case_ids is None or case_id in allowed_case_ids):
        case_query = (
            db.query(KnowledgeChunk)
            .join(KnowledgeSource)
            .filter(KnowledgeSource.case_id == case_id, active_source_filter)
        )
        case_scored = _vector_store_score_chunks(
            db,
            query=query,
            query_embedding=query_embedding,
            top_k=case_slots,
            case_id=case_id,
        )
        if not case_scored:
            case_scored = _score_chunks(case_query)
        case_scored = rerank_chunks(query, case_scored[:max(case_slots * 4, get_settings().reranker_top_k)], top_k=case_slots)

    filters = {
        "scope": "case_and_global" if case_id is not None else "global",
        "global_slots": global_slots,
        "case_slots": case_slots if case_id is not None else 0,
    }
    if case_id is not None:
        filters["case_id"] = case_id

    selected = global_scored + case_scored
    selected.sort(key=lambda item: item[0], reverse=True)
    run = _new_retrieval_run(db, task_id=task_id, query=query, filters=filters, top_k=top_k, selected=selected[:top_k])

    results: list[KnowledgeSearchResult] = []
    rank = 1
    for score, chunk in global_scored:
        db.add(RetrievalResult(retrieval_run_id=run.id, chunk_id=chunk.id, score=score, rank=rank))
        source = chunk.source
        results.append(
            KnowledgeSearchResult(
                source_id=source.id,
                chunk_id=chunk.id,
                title=source.title,
                source_type=source.source_type,
                scope="global",
                score=round(score, 4),
                rank=rank,
                snippet=chunk.text[:500],
                metadata_json={**(source.metadata_json or {}), **(chunk.metadata_json or {})},
            )
        )
        rank += 1

    for score, chunk in case_scored:
        db.add(RetrievalResult(retrieval_run_id=run.id, chunk_id=chunk.id, score=score, rank=rank))
        source = chunk.source
        results.append(
            KnowledgeSearchResult(
                source_id=source.id,
                chunk_id=chunk.id,
                title=source.title,
                source_type=source.source_type,
                scope="case",
                score=round(score, 4),
                rank=rank,
                snippet=chunk.text[:500],
                metadata_json={**(source.metadata_json or {}), **(chunk.metadata_json or {})},
            )
        )
        rank += 1

    return run, results
