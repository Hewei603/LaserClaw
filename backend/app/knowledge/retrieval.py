"""Knowledge retrieval services."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import KnowledgeChunk, KnowledgeSource, RetrievalResult, RetrievalRun
from ..schemas import Citation, KnowledgeSearchResult
from .embeddings import cosine_similarity, embed_text, tokenize


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


def search_knowledge(
    db: Session,
    *,
    query: str,
    case_id: int | None = None,
    source_type: str | None = None,
    top_k: int = 5,
    task_id: int | None = None,
) -> tuple[RetrievalRun, list[KnowledgeSearchResult]]:
    """Search knowledge chunks and persist a retrieval audit record."""
    query_embedding = embed_text(query)
    chunk_query = db.query(KnowledgeChunk).join(KnowledgeSource)
    filters: dict[str, object] = {}
    if case_id is not None:
        chunk_query = chunk_query.filter(KnowledgeSource.case_id == case_id)
        filters["case_id"] = case_id
    if source_type:
        chunk_query = chunk_query.filter(KnowledgeSource.source_type == source_type)
        filters["source_type"] = source_type

    scored: list[tuple[float, KnowledgeChunk]] = []
    for chunk in chunk_query.all():
        score = cosine_similarity(query_embedding, chunk.embedding or {}) * _domain_boost(query, chunk.source, chunk)
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    selected = scored[:top_k]

    run = RetrievalRun(task_id=task_id, query=query, filters_json=filters, top_k=top_k)
    db.add(run)
    db.flush()

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
) -> tuple[RetrievalRun, list[KnowledgeSearchResult]]:
    """Two-tier retrieval: global lab docs always fill first N slots (the 'constitution'),
    then case-specific attachments fill the remaining slots.

    This guarantees lab-wide SOPs, safety rules, and equipment catalogs are always
    present in context regardless of how relevant the case attachments are.
    """
    query_embedding = embed_text(query)

    def _score_chunks(chunk_query) -> list[tuple[float, KnowledgeChunk]]:
        scored: list[tuple[float, KnowledgeChunk]] = []
        for chunk in chunk_query.all():
            score = cosine_similarity(query_embedding, chunk.embedding or {}) * _domain_boost(query, chunk.source, chunk)
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored

    # --- Tier 1: global lab documents (always retrieved) ---
    global_query = db.query(KnowledgeChunk).join(KnowledgeSource).filter(KnowledgeSource.case_id.is_(None))
    global_scored = _score_chunks(global_query)[:global_slots]

    # --- Tier 2: case-specific attachments (only when a case is linked) ---
    case_scored: list[tuple[float, KnowledgeChunk]] = []
    if case_id is not None:
        case_query = db.query(KnowledgeChunk).join(KnowledgeSource).filter(KnowledgeSource.case_id == case_id)
        case_scored = _score_chunks(case_query)[:case_slots]

    filters = {
        "scope": "case_and_global" if case_id is not None else "global",
        "global_slots": global_slots,
        "case_slots": case_slots if case_id is not None else 0,
    }
    if case_id is not None:
        filters["case_id"] = case_id

    run = RetrievalRun(task_id=task_id, query=query, filters_json=filters, top_k=top_k)
    db.add(run)
    db.flush()

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
