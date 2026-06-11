"""Optional vector database adapters for knowledge chunks."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import KnowledgeChunk, KnowledgeSource

logger = logging.getLogger(__name__)


def _dense_values(embedding: dict[str, Any] | None) -> list[float] | None:
    if not embedding:
        return None
    values = embedding.get("values")
    if isinstance(values, list):
        return [float(value) for value in values]
    return None


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(str(float(v)) for v in values) + "]"


def _validate_pgvector_dimension(values: list[float]) -> None:
    settings = get_settings()
    if len(values) != settings.pgvector_dimension:
        raise RuntimeError(
            "pgvector embedding dimension mismatch: "
            f"got {len(values)}, expected {settings.pgvector_dimension}. "
            "Set PGVECTOR_DIMENSION and rebuild the knowledge_chunk_vectors migration/table "
            "to match EMBEDDING_MODEL."
        )


# ---------------------------------------------------------------------------
# Chroma adapter
# ---------------------------------------------------------------------------

def _chroma_collection():
    settings = get_settings()
    try:
        import chromadb
    except ImportError as exc:
        raise RuntimeError("RETRIEVAL_BACKEND=chroma requires chromadb. Install backend requirements first.") from exc

    client = chromadb.PersistentClient(path=settings.vector_store_dir)
    return client.get_or_create_collection(name="laserclaw_knowledge")


def _index_chroma_chunks(source: KnowledgeSource) -> None:
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


def _query_chroma_chunk_ids(
    *,
    query_embedding: dict[str, Any],
    top_k: int,
    case_id: int | None = None,
    source_type: str | None = None,
) -> list[tuple[int, float]]:
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
    logger.info("Chroma returned %s chunk ids", len(ids))

    output: list[tuple[int, float]] = []
    for raw_id, distance in zip(ids, distances):
        try:
            chunk_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        score = max(0.0, 1.0 - float(distance))
        output.append((chunk_id, score))
    return output


# ---------------------------------------------------------------------------
# pgvector adapter
# ---------------------------------------------------------------------------

def _index_pgvector_chunks(db: Session, source: KnowledgeSource) -> None:
    db.flush()
    db.execute(
        text("DELETE FROM knowledge_chunk_vectors WHERE source_id = :source_id"),
        {"source_id": source.id},
    )
    for chunk in source.chunks:
        vector = _dense_values(chunk.embedding)
        if not vector:
            continue
        _validate_pgvector_dimension(vector)
        db.execute(
            text("""
                INSERT INTO knowledge_chunk_vectors
                    (chunk_id, source_id, case_id, source_type, embedding_model, embedding)
                VALUES
                    (:chunk_id, :source_id, :case_id, :source_type, :embedding_model, CAST(:embedding AS vector))
                ON CONFLICT (chunk_id) DO UPDATE SET
                    source_id = EXCLUDED.source_id,
                    case_id = EXCLUDED.case_id,
                    source_type = EXCLUDED.source_type,
                    embedding_model = EXCLUDED.embedding_model,
                    embedding = EXCLUDED.embedding
            """),
            {
                "chunk_id": chunk.id,
                "source_id": source.id,
                "case_id": source.case_id or 0,
                "source_type": source.source_type,
                "embedding_model": (chunk.embedding or {}).get("model"),
                "embedding": _vector_literal(vector),
            },
        )
    logger.info("pgvector indexed %s chunks for source_id=%s", len(source.chunks), source.id)


def _query_pgvector_chunk_ids(
    db: Session,
    *,
    query_embedding: dict[str, Any],
    top_k: int,
    case_id: int | None = None,
    source_type: str | None = None,
) -> list[tuple[int, float]]:
    vector = _dense_values(query_embedding)
    if not vector:
        return []
    _validate_pgvector_dimension(vector)

    where_clauses: list[str] = []
    params: dict[str, Any] = {
        "query_vector": _vector_literal(vector),
        "limit": top_k,
    }
    if case_id is not None:
        where_clauses.append("case_id = :case_id")
        params["case_id"] = case_id
    if source_type:
        where_clauses.append("source_type = :source_type")
        params["source_type"] = source_type

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    rows = db.execute(
        text(f"""
            SELECT chunk_id, 1 - (embedding <=> CAST(:query_vector AS vector)) AS score
            FROM knowledge_chunk_vectors
            {where_sql}
            ORDER BY embedding <=> CAST(:query_vector AS vector)
            LIMIT :limit
        """),
        params,
    ).fetchall()
    result = [(int(row[0]), float(row[1])) for row in rows]
    logger.info("pgvector returned %s chunk ids", len(result))
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def index_source_chunks(db: Session, source: KnowledgeSource) -> None:
    """Index dense chunk embeddings in the configured vector DB.

    The SQL JSON store remains authoritative for metadata and fallback search.
    """
    settings = get_settings()
    backend = settings.retrieval_backend.lower()
    if backend == "pgvector":
        _index_pgvector_chunks(db, source)
        return
    if backend == "chroma":
        db.flush()
        _index_chroma_chunks(source)
        return


def query_chunk_ids(
    db: Session,
    *,
    query_embedding: dict[str, Any],
    top_k: int,
    case_id: int | None = None,
    source_type: str | None = None,
) -> list[tuple[int, float]]:
    settings = get_settings()
    backend = settings.retrieval_backend.lower()
    if backend == "pgvector":
        return _query_pgvector_chunk_ids(
            db,
            query_embedding=query_embedding,
            top_k=top_k,
            case_id=case_id,
            source_type=source_type,
        )
    if backend == "chroma":
        return _query_chroma_chunk_ids(
            query_embedding=query_embedding,
            top_k=top_k,
            case_id=case_id,
            source_type=source_type,
        )
    return []


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
