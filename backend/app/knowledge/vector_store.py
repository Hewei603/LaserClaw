"""Optional vector database adapters for knowledge chunks."""
from __future__ import annotations

from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import KnowledgeChunk, KnowledgeSource


def _dense_values(embedding: dict[str, Any] | None) -> list[float] | None:
    if not embedding:
        return None
    values = embedding.get("values")
    if isinstance(values, list):
        return [float(value) for value in values]
    return None


def _chroma_collection():
    settings = get_settings()
    try:
        import chromadb
    except ImportError as exc:
        raise RuntimeError("RETRIEVAL_BACKEND=chroma requires chromadb. Install backend requirements first.") from exc

    client = chromadb.PersistentClient(path=settings.vector_store_dir)
    return client.get_or_create_collection(name="laserclaw_knowledge")


def index_source_chunks(db: Session, source: KnowledgeSource) -> None:
    """Index dense chunk embeddings in the configured vector DB.

    The SQL JSON store remains authoritative for metadata and fallback search.
    Chroma is used only when explicitly configured and dense embeddings exist.
    """
    settings = get_settings()
    if settings.retrieval_backend.lower() != "chroma":
        return

    db.flush()
    chunks = list(source.chunks)
    ids: list[str] = []
    embeddings: list[list[float]] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []
    for chunk in chunks:
        vector = _dense_values(chunk.embedding)
        if not vector:
            continue
        ids.append(str(chunk.id))
        embeddings.append(vector)
        documents.append(chunk.text)
        metadatas.append(
            {
                "source_id": source.id,
                "case_id": source.case_id or 0,
                "source_type": source.source_type,
                "title": source.title,
                "chunk_index": chunk.chunk_index,
            }
        )
    if not ids:
        return

    collection = _chroma_collection()
    try:
        collection.delete(where={"source_id": source.id})
    except Exception:
        pass
    collection.upsert(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)


def query_chunk_ids(
    *,
    query_embedding: dict[str, Any],
    top_k: int,
    case_id: int | None = None,
    source_type: str | None = None,
) -> list[tuple[int, float]]:
    settings = get_settings()
    if settings.retrieval_backend.lower() != "chroma":
        return []

    vector = _dense_values(query_embedding)
    if not vector:
        return []

    where: dict[str, Any] = {}
    if case_id is not None:
        where["case_id"] = case_id
    if source_type:
        where["source_type"] = source_type

    collection = _chroma_collection()
    result = collection.query(
        query_embeddings=[vector],
        n_results=top_k,
        where=where or None,
        include=["distances"],
    )
    ids = result.get("ids", [[]])[0]
    distances = result.get("distances", [[]])[0]
    output: list[tuple[int, float]] = []
    for raw_id, distance in zip(ids, distances):
        try:
            chunk_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        score = max(0.0, 1.0 - float(distance))
        output.append((chunk_id, score))
    return output


def chunks_by_ids(db: Session, scored_ids: list[tuple[int, float]]) -> list[tuple[float, KnowledgeChunk]]:
    if not scored_ids:
        return []
    ids = [chunk_id for chunk_id, _ in scored_ids]
    chunks = (
        db.query(KnowledgeChunk)
        .join(KnowledgeSource)
        .filter(
            KnowledgeChunk.id.in_(ids),
            or_(KnowledgeSource.governance_status.is_(None), KnowledgeSource.governance_status != "archived"),
        )
        .all()
    )
    by_id = {chunk.id: chunk for chunk in chunks}
    return [(score, by_id[chunk_id]) for chunk_id, score in scored_ids if chunk_id in by_id]
